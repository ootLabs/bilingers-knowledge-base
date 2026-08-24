import { DEFAULT_LOCALE, type Locale } from "./config";
import { getDictionary } from "./translations";

export { DEFAULT_LOCALE, SUPPORTED_LOCALES } from "./config";
export type { Locale } from "./config";

type Dictionary = ReturnType<typeof getDictionary>;

function readPath(dictionary: Dictionary, key: string): string | undefined {
  const value = key.split(".").reduce<unknown>((node, segment) => {
    if (node && typeof node === "object" && segment in node) {
      return (node as Record<string, unknown>)[segment];
    }
    return undefined;
  }, dictionary);
  return typeof value === "string" ? value : undefined;
}

// Single locale today, so translation is a synchronous lookup rather than a
// context provider with client-side switching. That is deliberately not
// built yet: nothing in T-14's scope activates a second language, and
// building the switch now would be guessing at a UI nobody has asked for.
export function getTranslations(locale: Locale = DEFAULT_LOCALE) {
  const dictionary = getDictionary(locale);

  return function t(key: string): string {
    const value = readPath(dictionary, key);
    if (value === undefined) {
      if (process.env.NODE_ENV !== "production") {
        console.warn(`[i18n] missing translation key: "${key}"`);
      }
      return key;
    }
    return value;
  };
}
