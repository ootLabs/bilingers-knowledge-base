# Map - frontend

Next.js 15, App Router, TypeScript. All user-facing copy is **Polish**; identifiers and comments are English.

| Path | What's in it |
|---|---|
| `frontend/app/layout.tsx` | Root layout, `metadata` (title/description), `<html lang="pl">`, imports global styles |
| `frontend/app/page.tsx` | Landing page (`/`) - placeholder copy, reads `NEXT_PUBLIC_API_URL` |
| `frontend/app/globals.css` | CSS variables (light/dark via `prefers-color-scheme`), base body styles |
| `frontend/next.config.mjs` | Next.js config - `reactStrictMode` only |
| `frontend/tsconfig.json` | TypeScript config, `strict: true`, `@/*` path alias |
| `frontend/package.json` | Dependencies and the `dev`/`build`/`start`/`lint`/`typecheck`/`test` scripts |
| `frontend/vitest.config.ts` | Vitest setup: jsdom, coverage provider and thresholds, which files are tested |
| `frontend/vitest.setup.ts` | Loads jest-dom matchers, clears the DOM between tests |

## Tests

`docker compose exec frontend npm test`. See [`../testing.md`](../testing.md) for the full picture.

| Path | What's in it |
|---|---|
| `frontend/app/page.test.tsx` | Landing page rendering, Polish copy, and both branches of the API URL fallback |
| `frontend/app/layout.test.tsx` | Document language, children passthrough, exported `metadata` |

## Where new things go

| Adding | Goes in | Then |
|---|---|---|
| A page/route | `frontend/app/<feature>/page.tsx` | Add a row above |
| A shared component | `frontend/components/<Name>.tsx` | Only once it is reused twice; create the folder with the first file |
| An API call | `frontend/lib/api-client.ts` | One client, not `fetch` scattered across components |
| User-facing text | The component, in Polish | Keep it out of the backend - see `../llm/i18n.md` before hardcoding |

No component library, state manager, or styling framework is installed. Adding one is a decision worth recording in `../architecture.md`, not a drive-by `npm install`.
