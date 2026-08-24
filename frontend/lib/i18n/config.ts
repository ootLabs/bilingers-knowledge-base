// Only "pl" ships today (see docs/llm/i18n.md). The union type below is
// derived from this array so a new locale is one array entry, not a
// separately maintained type.
export const SUPPORTED_LOCALES = ["pl"] as const;

export type Locale = (typeof SUPPORTED_LOCALES)[number];

export const DEFAULT_LOCALE: Locale = "pl";
