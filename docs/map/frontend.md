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
| `frontend/app/panel/layout.tsx` | Shell for every `/panel` route: the `.panel` section plus `PanelGuard` around the children |
| `frontend/app/panel/PanelGuard.tsx` | Client guard for `/panel/*`: renders the "checking access" state, sends anyone with no token to `/panel/login`, and lets the login route itself through so it cannot redirect to itself. Not the security boundary (the backend refuses every tokenless request), it is what stops a signed-out person seeing a screenful of failed calls |
| `frontend/app/panel/PanelNav.tsx` | The panel's navigation and the only way to sign out: links to documents, security and (administrators only, read from the role the login stored) the change journal, plus a button that ends the session on the server and locally. Hides itself on the login route. Before it existed two screens were reachable only by typing their address |
| `frontend/app/panel/use-session-recovery.ts` | `useSessionRecovery()` - turns anything a panel call threw into a `PanelFailure`, except the two answers that are not messages: `not_authenticated` clears the token and hands over to the login screen, and an abort (a read the screen itself superseded) returns nothing to render |
| `frontend/app/panel/documents/page.tsx` | Documents route (`/panel/documents`) - heading, lead copy, mounts `DocumentsList` |
| `frontend/app/panel/documents/DocumentsList.tsx` | The editor's landing screen (T-86): loads every document with its newest version, shows the status pill, date and author on each row, and filters by title, status and date order in the browser (the whole list is already in hand, so a round trip per keystroke would feel slower than scrolling). An empty base and a filtered-away list get different ways onward |
| `frontend/app/panel/documents/DocumentForm.tsx` | The three writing fields (title, body, change comment) shared by the create and edit screens, fully controlled by whichever screen mounts it so a refused save leaves the text on screen |
| `frontend/app/panel/security/page.tsx` | Second factor route (`/panel/security`) - heading, lead copy, mounts `TwoFactorSetup` |
| `frontend/app/panel/security/TwoFactorSetup.tsx` | Turning the second factor on and off (T-83), written for somebody who has never heard the word TOTP: install an app, type this key, confirm with a code, keep the printed codes. The key is shown as text because no QR library is installed and adding one is a decision for `../architecture.md` |
| `frontend/app/panel/audit/page.tsx` | Journal route (`/panel/audit`) - heading, lead copy, mounts `AuditLog` |
| `frontend/app/panel/audit/AuditLog.tsx` | The change journal (T-89), read only and visibly so: no row is clickable and no action exists. Filters by person and date range, translates each action key, and prints an unknown key rather than leaving a line blank. Cancels a read the next one replaces, because the filter form stays clickable while one runs |
| `frontend/app/panel/documents/import/page.tsx` | Import route (`/panel/documents/import`) - heading, lead copy, mounts `DocumentImport` |
| `frontend/app/panel/documents/import/DocumentImport.tsx` | Two-step `.docx` import (T-85): read the file, show the report and the parsed text, then either save it as a new draft or as the next version of an existing document. Nothing is written until the editor accepts, and rejecting costs one click |
| `frontend/app/panel/documents/new/page.tsx` | New document route (`/panel/documents/new`) - heading, lead copy, mounts `NewDocumentForm` |
| `frontend/app/panel/documents/new/NewDocumentForm.tsx` | Creates a document as version 1 in the draft state, then opens the editor for it. Never clears the typed text on a failure: it is the only copy |
| `frontend/app/panel/documents/[id]/page.tsx` | Editor route (`/panel/documents/<id>`) - awaits the async `params`, refuses a non-numeric id with `notFound()`, mounts `DocumentEditor` |
| `frontend/app/panel/documents/[id]/DocumentEditor.tsx` | The editor (T-87): shows which version and date the text came from and whether it is published, saves through POST `/versions` so the previous snapshot survives, says what happened in a sentence after saving, and holds the typed text through a 409. No autosave, deliberately |
| `frontend/app/panel/documents/[id]/PublicationControls.tsx` | Publish and withdraw (T-88), below the editor rather than beside the save button so one is not clicked in place of the other. Says in plain words whether the assistant is using this version, since when and by whom |
| `frontend/app/panel/documents/[id]/history/page.tsx` | History route (`/panel/documents/<id>/history`) - same async `params` handling, mounts `VersionHistory` |
| `frontend/app/panel/documents/[id]/history/VersionHistory.tsx` | Every version with its date, author, comment and status; previews an older one against the current one as a line diff; restores by copying forward, so the list gets longer and never shorter. The Polish note recorded against a restore is written here, not in the backend |
| `frontend/app/panel/login/page.tsx` | Panel login route (`/panel/login`) - heading and lead copy, mounts `LoginForm` |
| `frontend/app/panel/login/LoginForm.tsx` | Client component owning the login form: one message for every refusal (the backend answers them identically on purpose), an outage rendered as an outage rather than as wrong credentials, and `/panel/documents` on success |
| `frontend/app/globals.css` | Design tokens as CSS variables (colors, spacing, font, button radius), mobile first base layout, `:focus-visible` outline. Brand color/font/button-radius tokens are sourced from T-03 and marked provisional in a comment at the top of the file, see `../llm/i18n.md` and T-03 in Trello for why. Only tokens an existing rule consumes are defined, add the next one alongside its first consumer. Also the T-63 state styles (`.status-message`, `.chat-*`, `.typing-indicator`) and `--color-danger`, which is border-only on purpose so the 3:1 non-text threshold applies |
| `frontend/components/SiteHeader.tsx` | Shared nav: brand link plus links to the four skeleton routes, labels via `lib/i18n` |
| `frontend/components/StatusMessage.tsx` | Shared "what happened plus one way onward" block used by all five state screens (chat empty/error/limit, 404, 500). Tone is a left border only, never text color |
| `frontend/components/StatusPill.tsx` | One status as a bordered pill with the word in it (szkic, w recenzji, opublikowany, wycofany), reused by the list, the editor and the history. Tone is the border, never the text color |
| `frontend/components/PlaceholderRoute.tsx` | Shared body for the empty skeleton routes (chat/quiz/account): takes `headingKey`/`placeholderKey`, renders heading plus placeholder copy via `lib/i18n` |
| `frontend/lib/api-client.ts` | The only place the browser calls the backend: `API_URL`, `streamAnswer` (POST `/chat`, yields the stream), `createSessionToken`, `ChatRequestError` and the `ChatFailure` vocabulary that HTTP statuses collapse into. Never reads a failed response's body, and always cancels the body before releasing the reader lock |
| `frontend/lib/panel-documents.ts` | Document calls on top of `panel-client.ts`: `DocumentStatus`, `VersionSummary`/`VersionDetail`, `DocumentSummary`/`DocumentDetail`, `listDocuments`, `getDocument`, `createDocument`, `saveVersion` (POST, never PUT), `listVersions`, `getVersion`, `publishVersion`, `withdrawVersion`, `restoreVersion`, plus `documentState`, `hasUnpublishedChanges`, `matchesStatus` and `searchableTitles`, which answer what the DOCUMENT's state and titles are rather than only its newest version's. The one place the backend's snake_case is converted to camelCase |
| `frontend/lib/panel-two-factor.ts` | `getTwoFactorStatus`, `startTwoFactorEnrolment`, `confirmTwoFactor`, `disableTwoFactor` and their types - the panel's second factor as seen from the browser |
| `frontend/lib/panel-audit.ts` | `listAuditEvents(filters, signal)`, `AuditEntry`, `AuditFilters` - reads the change journal. No writing counterpart, because the backend exposes none. Turns a "to" date into the whole of that day rather than its first second |
| `frontend/lib/panel-imports.ts` | `previewImport(file)`, `ImportPreview`, `ImportSkipped` - posts one `.docx` as multipart and returns what the backend understood. Reads only; accepting the result is an ordinary save through `panel-documents.ts` |
| `frontend/lib/text-diff.ts` | `diffLines`, `DiffLine` - line-level longest common subsequence between two versions, written rather than installed (a dependency is a decision for `../architecture.md`). Falls back to "these differ wholesale" past a cell budget instead of locking the tab |
| `frontend/lib/format-date.ts` | `formatDateTime` - one Polish date format for every panel screen; an unparseable value renders as nothing rather than as "Invalid Date" |
| `frontend/lib/panel-client.ts` | The panel's own HTTP client: `PanelFailure` (its second closed union, with 401/403/409 and without the parent's quota), `PanelRequestError`, `toPanelFailure`, `readPanelToken`/`storePanelToken`/`clearPanelToken` over `sessionStorage`, `panelLogin`, `panelRequest` (bearer token attached, a 401 drops it), `panelLogout`. Imports `API_URL` from `api-client.ts`; never reads a failed response's body |
| `frontend/lib/i18n/config.ts` | `SUPPORTED_LOCALES`, `DEFAULT_LOCALE`, the `Locale` type |
| `frontend/lib/i18n/locales/pl/index.ts` | The Polish dictionary in one object, assembled from its two halves. `translations.ts` types its registry against this, so a second locale still has to match the whole shape; both halves are `as const`, so every string stays a literal type |
| `frontend/lib/i18n/locales/pl/parent.ts` | Everything a parent sees: landing, chat, the shared `errors.*` failure keys and the routes still holding placeholder copy. Those keys and `chat.placeholder_answer.*` are snake_case because they are the API contract, not our naming: renaming one silently drops copy |
| `frontend/lib/i18n/locales/pl/panel.ts` | Everything the foundation sees: login, documents, editor, history, import, publication, the journal and the second factor. Split from the parent-facing half at the size limit, along the seam the product already has: two audiences who never read each other's screens |
| `frontend/lib/i18n/translations.ts` | `getDictionary(locale)`, the one place a new locale gets registered |
| `frontend/lib/i18n/index.ts` | `getTranslations(locale)`, the `t(key)` lookup components call, and `fill(template, values)` for the `{name}` placeholders that keep a sentence carrying a number whole in the dictionary instead of glued together in a component |
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
| `frontend/app/panel/security/TwoFactorSetup.test.tsx` | Instructions that never say "TOTP", the key shown then the printed codes, a wrong confirmation code keeping the key on screen, disabling refused without a code, the count of unused backup codes, and a missing encryption key read as our fault |
| `frontend/app/panel/audit/AuditLog.test.tsx` | Actions rendered as Polish rather than as keys, an unknown action still printed, the person and date range reaching the backend, no action offered on any row, an expired session redirecting, an editor's 403 read as a permissions answer rather than as an empty journal, and a superseded read cancelled rather than reported as an outage |
| `frontend/app/panel/documents/import/DocumentImport.test.tsx` | The report shown before anything is saved, rejecting a result without saving it, an accepted import becoming a new draft, importing into an existing document as its next version rather than a copy, and a refused file not leaving a broken preview on screen |
| `frontend/app/panel/documents/new/NewDocumentForm.test.tsx` | Both fields required, the editor opening for the document just created, and the typed text surviving a refused save |
| `frontend/app/panel/documents/[id]/DocumentEditor.test.tsx` | The version number and date on screen, the warning when the base version is published, saving through `saveVersion` (POST, not PUT) with the sentence that follows, a 409 leaving the text in the box, and an expired session redirecting |
| `frontend/app/panel/documents/[id]/PublicationControls.test.tsx` | A draft saying it is not what parents read, a published version naming who published it and when, publishing handing the new version back, withdrawal replacing publication once live, and a refused click still saying what happened |
| `frontend/app/panel/documents/[id]/history/VersionHistory.test.tsx` | Every version listed newest first, a restore producing more versions rather than fewer, the Polish note being sent from the frontend, the line-by-line comparison keeping unchanged lines, and no restore offered for the current version |
| `frontend/lib/text-diff.test.ts` | Identical texts, a rewritten line between unchanged ones, an insertion read as an insertion, a deletion read as a deletion, and the wholesale fallback past the cell budget |
| `frontend/app/panel/documents/DocumentsList.test.tsx` | The empty base offering one way onward, every row showing its status without a click, search and status filter narrowing the list, a filtered-away list reading differently from an empty one, an expired session redirecting to the login screen, and a retry after an outage |
| `frontend/app/panel/routes.test.tsx` | Every panel route in one file: that each renders its heading from the dictionary and mounts its client half, that the layout wraps a screen in the guard and the navigation, and that a non-numeric, zero or negative id becomes the 404 screen rather than a request the backend could only refuse. One file rather than eight, because they share one job and one set of failure modes |
| `frontend/app/panel/PanelNav.test.tsx` | That every screen an editor may use is linked, that the journal is offered to administrators only, and that signing out clears the token and leaves even when the backend does not answer |
| `frontend/app/panel/PanelGuard.test.tsx` | No token redirects to the login screen, the panel is never rendered while the guard is deciding, a stored token gets through, and the login route is not redirected to itself |
| `frontend/app/panel/login/LoginForm.test.tsx` | Both fields required, `/panel/documents` on success, a wrong password answering exactly as an unknown account does, a 503 shown as an outage rather than as bad credentials, the throttle as its own answer, and an unrecognised error degrading instead of reaching the screen |
| `frontend/lib/panel-documents.test.ts` | The snake_case to camelCase conversion happening once, a save posted with `POST` and not `PUT`, a missing comment sent as `null`, and every endpoint's path |
| `frontend/lib/panel-two-factor.test.ts` | Status, enrolment and confirmation shapes, a 422 turned into `invalid_code` (so a typo does not read as a dead session), and every other failure passing through |
| `frontend/lib/panel-audit.test.ts` | The query string built from the filters, a "to" date covering the whole day, a whitespace-only address ignored, and the response shape |
| `frontend/lib/panel-imports.test.ts` | The file posted as `FormData` (so the browser keeps the multipart boundary) and the report's shape |
| `frontend/lib/format-date.test.ts` | A readable Polish date, and an unparseable value rendering as nothing rather than "Invalid Date" |
| `frontend/lib/panel-client.test.ts` | Token storage, every status-to-failure mapping, a login 401 as `invalid_credentials` rather than an expiry, the bearer header, a mid-session 401 dropping the token, a 204 returning nothing, logout forgetting the token even when the backend does not answer, and that a failed response's body is never read |
| `frontend/lib/api-client.test.ts` | The posted field names, chunk order, a multi-byte character split across two chunks, every status-to-failure mapping, an unmapped status degrading to `unreachable`, an abort rethrown as-is, the body being cancelled when the caller stops reading early, and that a failed response's body is never read |
| `frontend/lib/i18n/index.test.ts` | Dot-path key resolution, the missing-key fallback, and its dev-only console warning |

## Where new things go

| Adding | Goes in | Then |
|---|---|---|
| A page/route | `frontend/app/<feature>/page.tsx` | Add a row above |
| A shared component | `frontend/components/<Name>.tsx` | Only once it is reused twice; create the folder with the first file |
| An API call | `frontend/lib/api-client.ts` | One client, not `fetch` scattered across components |
| User-facing text | `frontend/lib/i18n/locales/pl/` (`parent.ts` or `panel.ts`), read it with `getTranslations()` | Never hardcode strings in a component, see `../llm/i18n.md` |
| A second locale | `frontend/lib/i18n/locales/<code>.ts`, same keys as `pl.ts` | Register it in the `dictionaries` map in `frontend/lib/i18n/translations.ts`, nothing else changes |

No component library, state manager, or styling framework is installed. Adding one is a decision worth recording in `../architecture.md`, not a drive-by `npm install`.
