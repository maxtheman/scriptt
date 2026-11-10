// The scriptt.ai site: static files only. build.sh copies web/site into public/.
import { defineConfig } from "cf/config";

export default defineConfig({
  worker: {
    name: "scriptt-site",
    compatibilityDate: "2026-09-21",
    assets: { htmlHandling: "auto-trailing-slash", notFoundHandling: "404-page" },
    domains: ["scriptt.ai", "www.scriptt.ai"],
    observability: { enabled: true },
  },
});
