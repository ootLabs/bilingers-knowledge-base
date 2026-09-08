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
/**
 * Substitute `{name}` placeholders in a translated string.
 *
 * Exists so a sentence carrying a number ("Zapisano jako wersja 4.") stays one
 * sentence in the dictionary instead of being glued together from fragments in
 * a component. Polish inflects, so a fragment that reads correctly in one
 * sentence is wrong in the next, and a translator seeing halves cannot fix it.
 *
 * A placeholder with no value is left as it stands: printing "{version}" is
 * obviously broken and gets fixed, whereas silently dropping it produces a
 * sentence that looks finished and says the wrong thing.
 */
export function fill(template: string, values: Record<string, string | number>): string {
  return template.replace(/\{(\w+)\}/g, (placeholder, name: string) =>
    name in values ? String(values[name]) : placeholder,
  );
}

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
