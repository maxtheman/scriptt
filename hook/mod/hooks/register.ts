import type { Register } from 'claude-code'

// The scriptt hook as a mod. On each prompt it runs scriptt_hook.py, shows the first line of what the hook
// found, and attaches the hook's text for the model. With no d1 configured the hook prints nothing and the
// prompt goes through unchanged.
//   SCRIPTT_HOOK    the path of scriptt_hook.py (default ~/Documents/scriptt-release/hook/scriptt_hook.py)
//   SCRIPTT_PYTHON  a Python 3.14 or later (default python3.14)
export const register: Register = on => {
  on('prompt.submit', async ($, e, next) => {
    if (e.command) {
      return next(e)
    }

    const home = (await $.env.get('HOME')) ?? ''
    const hook = (await $.env.get('SCRIPTT_HOOK')) ?? `${home}/Documents/scriptt-release/hook/scriptt_hook.py`
    const python = (await $.env.get('SCRIPTT_PYTHON')) ?? 'python3.14'
    const event = JSON.stringify({ hook_event_name: 'UserPromptSubmit', prompt: e.text, session_id: 'mod' })
    let context: string | undefined

    try {
      const { exitCode, stdout } = await $.process.run([python, hook], { stdin: event, timeoutMs: 60000 })

      if (exitCode === 0 && stdout.trim()) {
        context = JSON.parse(stdout).hookSpecificOutput?.additionalContext
      }
    } catch {
      context = undefined
    }

    if (!context) {
      return next(e)
    }

    $.ui.toast(context.split('\n')[1] ?? 'scriptt hook ran')

    return next({ ...e, context: [...(e.context ?? []), context] })
  })
}
