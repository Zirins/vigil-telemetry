"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { ThemeToggle } from "@/components/ThemeToggle";
import { cn } from "@/lib/utils";

export function AppNav() {
  const pathname = usePathname();

  const isActive = (href: string) =>
    href === "/" ? pathname === "/" : pathname.startsWith(href);

  return (
    <header className="sticky top-0 z-50 border-b border-border bg-card/95 backdrop-blur-sm">
      <div className="mx-auto flex h-11 max-w-[1380px] items-center justify-between px-4 sm:px-6">
        <div className="flex items-center gap-6">
          <Link href="/" className="flex items-center gap-2">
            <span className="font-bold tracking-tight text-foreground text-sm font-mono">
              VIGIL
            </span>
          </Link>

          <nav aria-label="Primary navigation" className="flex h-11 items-center gap-4">
            {[
              { href: "/", label: "Services" },
              { href: "/incidents", label: "Incidents" },
            ].map(({ href, label }) => (
              <Link
                key={href}
                href={href}
                className={cn(
                  "relative flex h-full items-center px-1 text-xs font-medium transition-colors duration-150",
                  isActive(href)
                    ? "text-primary font-semibold border-b-2 border-primary"
                    : "text-muted-foreground hover:text-foreground"
                )}
              >
                {label}
              </Link>
            ))}
          </nav>
        </div>

        <div className="flex items-center gap-3">
          <ThemeToggle />
        </div>
      </div>
    </header>
  );
}
