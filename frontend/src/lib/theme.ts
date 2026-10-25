export type ColorScheme = "light" | "dark";

export const COLOR_SCHEME_STORAGE_KEY = "vigil-color-scheme";

export function getStoredColorScheme(): ColorScheme {
  if (typeof window === "undefined") return "light";
  const stored = localStorage.getItem(COLOR_SCHEME_STORAGE_KEY);
  return stored === "dark" ? "dark" : "light";
}

export function applyColorScheme(scheme: ColorScheme): void {
  if (scheme === "dark") {
    document.documentElement.classList.add("dark");
  } else {
    document.documentElement.classList.remove("dark");
  }
  localStorage.setItem(COLOR_SCHEME_STORAGE_KEY, scheme);
}
