// The font files every page needs at once (T-512): Onest for the text and Unbounded for headings,
// Cyrillic and Latin. Preloaded from <head>, so they load together with the CSS and not after it:
// on a phone this takes the first paint of the landing from ~2.1 s to ~1.4 s (Lighthouse, mobile).
// The same files the fontsource CSS points to — the import gives their address after the build.
import onestCyrillic from "@fontsource-variable/onest/files/onest-cyrillic-wght-normal.woff2";
import onestLatin from "@fontsource-variable/onest/files/onest-latin-wght-normal.woff2";
import unboundedCyrillic from "@fontsource-variable/unbounded/files/unbounded-cyrillic-wght-normal.woff2";
import unboundedLatin from "@fontsource-variable/unbounded/files/unbounded-latin-wght-normal.woff2";

export const PRELOAD_FONTS = [onestCyrillic, onestLatin, unboundedCyrillic, unboundedLatin];
