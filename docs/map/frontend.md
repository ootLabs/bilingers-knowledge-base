# Map - frontend

Next.js 15, App Router, TypeScript. All user-facing copy is **Polish**; identifiers and comments are English.

| Path | What's in it |
|---|---|
| `frontend/app/layout.tsx` | Root layout: `<html lang="pl">`, loads Poppins via `next/font/google`, renders `SiteHeader`, `metadata` (title/description) sourced through `lib/i18n` |
| `frontend/app/page.tsx` | Landing page (`/`) - copy via `lib/i18n`, shows the `API_URL` the client itself uses (imported from `lib/api-client`), links to `/chat` |
| `frontend/app/chat/page.tsx` | Chat route (`/chat`) - heading plus `ChatPanel`, no logic of its own |
| `frontend/app/chat/ChatPanel.tsx` | Client component owning the four T-63 states (empty, waiting, answering, failed): question box, submit, and the streamed answer. Picks the one way onward per failure: the limit sends the parent to registration, a 422 returns the cursor to the box (the same wording would only be refused again), everything else re-sends the question that was asked. Resolves the translation keys the backend streams into copy, drops any it cannot resolve, and fails rather than showing a blank answer if none of them resolve. The status region is `aria-live="polite"` but `aria-busy` while the answer grows, so it is announced once instead of per chunk. The conversation proper (history, follow-up threads, T-61's entry screen) is T-62, not here |
| `frontend/app/chat/TypingIndicator.tsx` | The "asystent pisze" state, shown on submit rather than on first byte; labelled text plus dots hidden from assistive technology |
| `frontend/app/not-found.tsx` | 404 screen - own heading, `StatusMessage`, link home. Renders no status code |
| `frontend/app/error.tsx` | 500 screen (App Router error boundary) - `reset` plus a link home. Deliberately never destructures the thrown `Error`, see the file comment |
| `frontend/app/quiz/page.tsx` | Quiz route (`/quiz`) - renders `PlaceholderRoute` with the quiz keys, intentionally empty per T-14 scope |
| `frontend/app/account/page.tsx` | Account route (`/account`) - renders `PlaceholderRoute` with the account keys, intentionally empty per T-14 scope |
| `frontend/app/globals.css` | Design tokens as CSS variables (colors, spacing, font, button radius), mobile first base layout, `:focus-visible` outline. Brand color/font/button-radius tokens are sourced from T-03 and marked provisional in a comment at the top of the file, see `../llm/i18n.md` and T-03 in Trello for why. Only tokens an existing rule consumes are defined, add the next one alongside its first consumer. Also the T-63 state styles (`.status-message`, `.chat-*`, `.typing-indicator`) and `--color-danger`, which is border-only on purpose so the 3:1 non-text threshold applies |
| `frontend/components/SiteHeader.tsx` | Shared nav: brand link plus links to the four skeleton routes, labels via `lib/i18n` |
| `frontend/components/StatusMessage.tsx` | Shared "what happened plus one way onward" block used by all five state screens (chat empty/error/limit, 404, 500). Tone is a left border only, never text color |
| `frontend/components/PlaceholderRoute.tsx` | Shared body for the empty skeleton routes (chat/quiz/account): takes `headingKey`/`placeholderKey`, renders heading plus placeholder copy via `lib/i18n` |
| `frontend/lib/api-client.ts` | The only place the browser calls the backend: `API_URL`, `streamAnswer` (POST `/chat`, yields the stream), `createSessionToken`, `ChatRequestError` and the `ChatFailure` vocabulary that HTTP statuses collapse into. Never reads a failed response's body, and always cancels the body before releasing the reader lock |
| `frontend/lib/i18n/config.ts` | `SUPPORTED_LOCALES`, `DEFAULT_LOCALE`, the `Locale` type |
| `frontend/lib/i18n/locales/pl.ts` | Polish dictionary, the only active locale today. `chat.placeholder_answer.*` and the `errors.*` failure keys are snake_case because they are the API contract, not our naming - renaming one silently drops copy |
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
| `frontend/app/chat/page.test.tsx` | Chat route renders the chat heading and mounts the panel (the panel itself is mocked) |
| `frontend/app/chat/ChatPanel.test.tsx` | All four states, that the typing state appears synchronously on submit, key reassembly across chunk boundaries, unknown keys dropped, retry re-sending the question that was asked, the limit sending the parent onward instead of retrying, a 422 focusing the box instead of re-sending, the live region staying busy until the answer settles, and that no unexpected error's detail reaches the screen |
| `frontend/app/chat/TypingIndicator.test.tsx` | The Polish label, and the dots being hidden from assistive technology |
| `frontend/app/not-found.test.tsx` | Polish heading, the way back, and no status code on screen |
| `frontend/app/error.test.tsx` | Polish heading, `reset` wired to the retry, the way back, and that neither the thrown message nor its digest is rendered |
| `frontend/app/quiz/page.test.tsx` | Quiz route wires up the quiz translation keys (renders the quiz heading) |
| `frontend/app/account/page.test.tsx` | Account route wires up the account translation keys (renders the account heading) |
| `frontend/components/SiteHeader.test.tsx` | Every nav link points at the right route with the right Polish label |
| `frontend/components/StatusMessage.test.tsx` | Translated title and description, the tone class, both action kinds, and no action when none is given |
| `frontend/components/PlaceholderRoute.test.tsx` | Renders the heading and placeholder copy for the keys it is given, the shared rendering logic all three placeholder routes reuse |
| `frontend/lib/api-client.test.ts` | The posted field names, chunk order, a multi-byte character split across two chunks, every status-to-failure mapping, an unmapped status degrading to `unreachable`, an abort rethrown as-is, the body being cancelled when the caller stops reading early, and that a failed response's body is never read |
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
