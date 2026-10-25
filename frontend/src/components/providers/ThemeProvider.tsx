"use client";

import { createContext, useCallback, useContext, useEffect, useState } from "react";
import { applyColorScheme, getStoredColorScheme, type ColorScheme } from "@/lib/theme";

interface ThemeContextValue {
  colorScheme: ColorScheme;
  setColorScheme: (scheme: ColorScheme) => void;
  toggleColorScheme: () => void;
}

const ThemeContext = createContext<ThemeContextValue | null>(null);

export function ThemeProvider({ children }: { children: React.ReactNode }) {
  const [colorScheme, setColorSchemeState] = useState<ColorScheme>("light");

  useEffect(() => {
    setColorSchemeState(getStoredColorScheme());
  }, []);

  const setColorScheme = useCallback((scheme: ColorScheme) => {
    setColorSchemeState(scheme);
    applyColorScheme(scheme);
  }, []);

  const toggleColorScheme = useCallback(() => {
    setColorSchemeState((current) => {
      const next: ColorScheme = current === "dark" ? "light" : "dark";
      applyColorScheme(next);
      return next;
    });
  }, []);

  return (
    <ThemeContext.Provider value={{ colorScheme, setColorScheme, toggleColorScheme }}>
      {children}
    </ThemeContext.Provider>
  );
}

const defaultContext: ThemeContextValue = {
  colorScheme: "light",
  setColorScheme: () => {},
  toggleColorScheme: () => {},
};

export function useTheme(): ThemeContextValue {
  return useContext(ThemeContext) ?? defaultContext;
}
