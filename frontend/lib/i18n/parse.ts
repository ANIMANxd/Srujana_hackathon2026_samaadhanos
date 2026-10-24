// Plain (non-client) module so server pages can parse ?lang= too.

export type Lang = "en" | "kn";

export function parseLang(raw: string | string[] | undefined): Lang {
  return raw === "kn" ? "kn" : "en";
}
