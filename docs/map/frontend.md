# Map - frontend

Next.js 15, App Router, TypeScript. All user-facing copy is **Polish**; identifiers and comments are English.

| Path | What's in it |
|---|---|
| `frontend/app/layout.tsx` | Root layout: `<html lang="pl">`, loads Poppins via `next/font/google`, renders `SiteHeader`, `metadata` (title/description) sourced through `lib/i18n` |
| `frontend/app/page.tsx` | Landing page (`/`) - copy via `lib/i18n`, reads `NEXT_PUBLIC_API_URL`, links to `/chat` |
| `frontend/app/chat/page.tsx` | Chat route (`/chat`) - renders `PlaceholderRoute` with the chat keys, no chat logic yet (that is T-63 and later) |
| `frontend/app/quiz/page.tsx` | Quiz route (`/quiz`) - renders `PlaceholderRoute` with the quiz keys, intentionally empty per T-14 scope |
| `frontend/app/account/page.tsx` | Account route (`/account`) - renders `PlaceholderRoute` with the account keys, intentionally empty per T-14 scope |
| `frontend/app/globals.css` | Design tokens as CSS variables (colors, spacing, font, button radius), mobile first base layout, `:focus-visible` outline. Brand color/font/button-radius tokens are sourced from T-03 and marked provisional in a comment at the top of the file, see `../llm/i18n.md` and T-03 in Trello for why. Only tokens an existing rule consumes are defined, add the next one alongside its first consumer |
| `frontend/components/SiteHeader.tsx` | Shared nav: brand link plus links to the four skeleton routes, labels via `lib/i18n` |
| `frontend/components/PlaceholderRoute.tsx` | Shared body for the empty skeleton routes (chat/quiz/account): takes `headingKey`/`placeholderKey`, renders heading plus placeholder copy via `lib/i18n` |
| `frontend/lib/i18n/config.ts` | `SUPPORTED_LOCALES`, `DEFAULT_LOCALE`, the `Locale` type |
| `frontend/lib/i18n/locales/pl.ts` | Polish dictionary, the only active locale today |
| `frontend/lib/i18n/translations.ts` | `getDictionary(locale)`, the one place a new locale gets registered |
| `frontend/lib/i18n/index.ts` | `getTranslations(locale)`, the `t(key)` lookup components call |
| `frontend/next.config.mjs` | Next.js config - `reactStrictMode` only |
| `frontend/tsconfig.json` | TypeScript config, `strict: true`, `@/*` path alias |
| `frontend/package.json` | Dependencies and the `dev`/`build`/`start`/`lint`/`typecheck`/`test` scripts |
| `frontend/vitest.config.ts` | Vitest setup: jsdom, `@/*` alias mirrored for Vite, coverage provider and thresholds, which files are tested |
| `frontend/vitest.setup.ts` | Loads jest-dom matchers, clears the DOM between tests, mocks `next/font/google` |

## Tests

`docker compose exec frontend npm test`. See [`../testing.md`](../testing.md) for the full picture.

| Path | What's in it |
|---|---|
| `frontend/app/page.test.tsx` | Landing page rendering, Polish copy, the chat link, and both branches of the API URL fallback |
| `frontend/app/layout.test.tsx` | Document language, header plus children in the body, exported `metadata` |
| `frontend/app/chat/page.test.tsx` | Chat route wires up the chat translation keys (renders the chat heading) |
| `frontend/app/quiz/page.test.tsx` | Quiz route wires up the quiz translation keys (renders the quiz heading) |
| `frontend/app/account/page.test.tsx` | Account route wires up the account translation keys (renders the account heading) |
| `frontend/components/SiteHeader.test.tsx` | Every nav link points at the right route with the right Polish label |
| `frontend/components/PlaceholderRoute.test.tsx` | Renders the heading and placeholder copy for the keys it is given, the shared rendering logic all three placeholder routes reuse |
| `frontend/lib/i18n/index.test.ts` | Dot-path key resolution, the missing-key fallback, and its dev-only console warning |

## Where new things go

| Adding | Goes in | Then |
|---|---|---|
| A page/route | `frontend/app/<feature>/page.tsx` | Add a row above |
| A shared component | `frontend/components/<Name>.tsx` | Only once it is reused twice; create the folder with the first file |
| An API call | `frontend/lib/api-client.ts` | One client, not `fetch` scattered across components |
| User-facing text | `frontend/lib/i18n/locales/pl.ts`, read it with `getTranslations()` | Never hardcode strings in a component, see `../llm/i18n.md` |
| A second locale | `frontend/lib/i18n/locales/<code>.ts`, same keys as `pl.ts` | Register it in the `dictionaries` map in `frontend/lib/i18n/translations.ts`, nothing else changes |

No component library, state manager, or styling framework is installed. Adding one is a decision worth recording in `../architecture.md`, not a drive-by `npm install`.
