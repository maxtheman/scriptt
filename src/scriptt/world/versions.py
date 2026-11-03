"""Versions of a project that git and DVC keep. You can run the steps and keep a version
and list versions. You can also read a
result as it was in any version. This needs the extra `scriptt[versions]` (DVC).

```python
from scriptt.world.versions import Project, Result


class ModelScore(Result, path="results/model.json"):
    model: str
    right: int


project = Project(".")
project.run()  # dvc repro: the steps whose inputs changed
project.keep(
    "R3 reads the entry date"
)  # git commit of code, settings, results and dvc.lock
for version in project.versions():
    print(version, version.read(ModelScore))
```
"""

import contextlib
import datetime as dt
import io
import json
import logging
import subprocess
from contextlib import contextmanager, redirect_stdout
from dataclasses import dataclass
from pathlib import Path
from typing import Any, ClassVar, Self


from pydantic import BaseModel, ConfigDict, ValidationError


@contextmanager
def _quiet():
    """DVC writes progress notes. A failed step still raises its error."""
    logger = logging.getLogger("dvc")
    level, logger.level = logger.level, logging.WARNING
    try:
        with redirect_stdout(io.StringIO()):
            yield
    finally:
        logger.setLevel(level)


from ._facts import Facts


class Result(BaseModel):
    """A result that a step writes and a version keeps. A result is a frozen Pydantic
    model.

    Declare where the result lives with `class Score(Result,
    path="results/score.json")`. The path is relative to the
    project folder.

    Example:
        ```python
        from scriptt.world.versions import Result


        class Score(Result, path="results/score.json"):
            model: str
            right: int


        Score(model="baseline", right=4).right  # -> 4
        Score.path  # -> 'results/score.json'
        ```
    """

    model_config = ConfigDict(frozen=True)
    path: ClassVar[str]

    def __init_subclass__(cls, path: str = "", **kwargs: Any) -> None:
        """Read the `path=` option of a subclass. An example is `class Score(Result,
        path="results/score.json")`.

        Args:
            path: The path of the result file. It is relative to the project folder. The
                default is an empty text. This keeps the path of the parent class.
        """
        super().__init_subclass__(**kwargs)
        if path:
            cls.path = path

    def save(self, project: Project | str | Path = ".") -> Path:
        """Write the result to the file that its type names, in the project folder.

        The folder of the file is made if it does not exist. The file contains JSON.

        Args:
            project: A `Project` or the path of the project folder. The default is
                `"."`. This is the current folder.

        Returns:
            The path of the file.

        Example:
            ```python
            # project: a Project
            # ModelScore: a Result with path="results/score.json"
            path = ModelScore(model="baseline", right=5).save(project)
            path.name  # -> 'score.json'
            ```
        """
        root = project.root if isinstance(project, Project) else Path(project)
        out = root / self.path
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(self.model_dump_json(indent=1) + "\n")
        return out


@dataclass(frozen=True, slots=True)
class Version:
    """1 kept version. It is a git commit. `Project.versions` and `Project.keep` make
    versions.

    Attributes:
        id: The short git hash of the commit.
        time: The time of the commit. It has no time zone.
        message: The message that you gave to `keep`.
        project: The project that keeps the version.
    """

    id: str
    time: dt.datetime
    message: str
    project: Project

    def read[R: Result](self, result: type[R]) -> R:
        """Read a result as this version kept it.

        Args:
            result: The `Result` type. Its `path` says which file to read.

        Returns:
            The result as a `result` object.

        Raises:
            pydantic.ValidationError: The file of that version does not fit the type.

        Example:
            ```python
            # project: a Project with 1 kept version
            # ModelScore: a Result with path="results/score.json"
            first = project.versions()[0]
            first.read(ModelScore).right  # -> 4
            ```
        """
        import dvc.api

        return result.model_validate_json(
            dvc.api.read(result.path, repo=str(self.project.root), rev=self.id)
        )

    def file(self, path: str) -> bytes:
        """Read any file as this version kept it. This includes code and settings and
        DVC data.

        Args:
            path: The path of the file, relative to the project folder.

        Returns:
            The content of the file as bytes.

        Example:
            ```python
            # project: a Project with 1 kept version
            project.versions()[0].file("params.yaml").decode().strip()
            # -> 'journals: 4'
            ```
        """
        import dvc.api

        return dvc.api.read(path, repo=str(self.project.root), rev=self.id, mode="rb")

    def __repr__(self) -> str:
        return f"{self.id}  {self.time:%d %b %H:%M}  {self.message}"


@dataclass(frozen=True, slots=True)
class Kept[R: Result]:
    """1 kept version and its result. `Project.results` makes it.

    Attributes:
        version: The kept version.
        result: The result as that version kept it.
        older_forms: The number of earlier versions that `Project.results` left out so
            far. Their file has a form
            that the type cannot read.
    """

    version: Version
    result: R
    older_forms: int


@dataclass(frozen=True, slots=True)
class Run:
    """1 run that `Project.try_settings` made and that you have not kept as a version.

    Attributes:
        name: The name that you gave to the run.
        settings: The settings of the run as a dictionary from name to value.
        results: The results of the run that DVC shows as a dictionary. It can be empty.
    """

    name: str
    settings: dict[str, Any]
    results: dict[str, Any]


@dataclass(frozen=True)
class Project:
    """A folder with git and DVC. `dvc.yaml` contains the steps and `params.yaml`
    contains the settings.

    The folder must be a git repository with DVC set up in that folder (it has `.dvc/`).
    Give the path of the folder
    to the constructor. A project runs DVC and git commands. These change the current
    folder and print while they
    run. So use 1 project at a time in a process.

    Args:
        root: The path of the project folder. `~` is expanded and the path is made
            absolute.

    Raises:
        ValueError: The folder has no `.dvc/` folder. (DVC would use a parent project
            instead.)

    Example:
        ```python
        from scriptt.world.versions import Project

        Project(".").root.is_absolute()  # -> True
        ```
    """

    root: Path

    def __init__(self, root: str | Path) -> None:
        folder = Path(root).expanduser().resolve()
        if not (folder / ".dvc").is_dir():
            raise ValueError(f"{folder} has no .dvc folder: run `dvc init` there first")
        object.__setattr__(self, "root", folder)

    def _git(self, *args: str) -> str:
        done = subprocess.run(
            ["git", *args], cwd=self.root, capture_output=True, text=True
        )
        if done.returncode != 0:
            raise RuntimeError(
                f"git {' '.join(args[:2])} failed: "
                f"{(done.stderr or done.stdout).strip()}"
            )
        return done.stdout.strip()

    def run(self) -> Self:
        """Run the steps whose inputs changed (`dvc repro`).

        The steps run in the project folder. The current folder does not matter.

        Returns:
            The same project. So you can chain calls.

        Raises:
            dvc.stage.exceptions.StageFileDoesNotExistError: The project folder has no
                `dvc.yaml`.

        Example:
            ```python
            # project: a Project with 1 kept version
            project.run().root == project.root  # -> True
            ```
        """
        from dvc.repo import Repo

        with _quiet(), contextlib.chdir(self.root), Repo(str(self.root)) as repo:
            # DVC's decorator hides the signature
            repo.reproduce()  # pyright: ignore[reportCallIssue]
        return self

    def try_settings(self, name: str, **settings: Any) -> Run:
        """Run the steps with changed settings (`dvc exp run -S`). This does not make a
        new version. DVC keeps the run.

        Write a dotted setting name with `__`. For example the keyword `e3__journals`
        sets `e3.journals`. The steps run in the
        project folder. DVC leaves the trial settings in the working `params.yaml`. Set
        them back before `keep`.

        Args:
            name: The name of the run.
            **settings: The settings to change as keyword arguments.

        Returns:
            The `Run`.

        Example:
            ```python
            # project: a Project with 1 kept version and a setting called journals
            run = project.try_settings("more", journals=8)
            run.name, run.settings["journals"]  # -> ('more', 8.0)
            ```
        """
        from dvc.repo import Repo
        from dvc.repo.experiments.run import run

        changes = [
            f"params.yaml:{key.replace('__', '.')}={json.dumps(value)}"
            for key, value in settings.items()
        ]
        with _quiet(), contextlib.chdir(self.root), Repo(str(self.root)) as repo:
            # DVC's decorator hides the signature
            run(repo, params=changes, name=name)  # pyright: ignore[reportCallIssue]
        return next(r for r in self.runs() if r.name == name)

    def keep(self, message: str, *new_files: str | Path) -> Version:
        """Keep a new version: make a git commit.

        The commit contains these files.

        - Every file that git already tracks and that changed (code, settings, results
        and `dvc.lock`).
        - The new files that you name.

        Other new files stay out.

        Args:
            message: The commit message. It is the message of the version.
            *new_files: Paths of new files to add to git. The default is none.

        Returns:
            The new `Version`.

        Example:
            ```python
            # project: a Project with 1 kept version and a setting called journals
            from pathlib import Path

            Path("params.yaml").write_text("journals: 6")
            project.run()
            project.keep("more journals").message  # -> 'more journals'
            ```
        """
        self._git("add", "-u", "--", str(self.root))  # only the files of this project
        if new_files:
            self._git("add", "--", *map(str, new_files))
        self._git(
            "commit", "-q", "-m", message, "--", str(self.root)
        )  # only this project, whatever else is staged
        return self.versions()[-1]

    def versions(self, of: type[Result] | None = None) -> Facts[Version]:
        """List the kept versions, oldest first.

        Args:
            of: A `Result` type. The default `None` means every version. A type limits
                the list to the versions that changed that result file.

        Returns:
            A collection of `Version` objects.

        Example:
            ```python
            # project: a Project with 1 kept version
            # ModelScore: a Result with path="results/score.json"
            [version.message for version in project.versions()]  # -> ['first run']
            [version.message for version in project.versions(of=ModelScore)]
            # -> ['first run']
            ```
        """
        out = []
        where = (
            ["--", of.path] if of is not None else ["--", "."]
        )  # the commits that touch this project only
        for line in self._git(
            "log", "--reverse", "--format=%h%x1f%cI%x1f%s", *where
        ).splitlines():
            commit, time, message = line.split("\x1f")
            at = dt.datetime.fromisoformat(time)
            out.append(
                Version(
                    commit, at.astimezone(dt.UTC).replace(tzinfo=None), message, self
                )
            )  # in UTC, as `known` times are
        return Facts(out)

    def results[R: Result](self, of: type[R]) -> Facts[Kept[R]]:
        """List each version that changed a result. The result is read as a type. The
        oldest version comes first.

        A version whose file has an older form that the type cannot read is left out.
        `older_forms` on each `Kept` counts those
        versions so far.

        Args:
            of: The `Result` type to read.

        Returns:
            A collection of `Kept` objects.

        Example:
            ```python
            # project: a Project with 1 kept version
            # ModelScore: a Result with path="results/score.json"
            [kept.result.right for kept in project.results(ModelScore)]  # -> [4]
            ```
        """
        out, older = [], 0
        for version in self.versions(of=of):
            try:
                out.append(Kept(version, version.read(of), older))
            except ValidationError:
                older += 1
        return Facts(out)

    def runs(self) -> Facts[Run]:
        """List the runs from `try_settings` that you have not kept as versions.

        Returns:
            A collection of `Run` objects.

        Example:
            ```python
            # project: a Project with 1 kept version and a setting called journals
            project.try_settings("more", journals=8)
            [run.name for run in project.runs()]  # -> ['more']
            ```
        """
        import dvc.api
        import yaml

        def flat(tree: dict, prefix: str = "") -> set[str]:
            return {
                key
                for k, v in tree.items()
                for key in (
                    flat(v, f"{prefix}{k}.")
                    if isinstance(v, dict)
                    else {f"{prefix}{k}"}
                )
            }

        params = self.root / "params.yaml"
        names = (
            flat(yaml.safe_load(params.read_text()) or {}) if params.exists() else set()
        )
        rows = dvc.api.exp_show(repo=str(self.root))
        out = []
        for row in rows:
            if not row.get("Experiment"):
                continue
            settings = {k: v for k, v in row.items() if k in names}
            out.append(
                Run(
                    row["Experiment"],
                    settings,
                    {k: v for k, v in row.items() if k.startswith("results/")},
                )
            )
        return Facts(out)
