import { FlatCompat } from "@eslint/eslintrc";
import { dirname } from "path";
import { fileURLToPath } from "url";

const compat = new FlatCompat({ baseDirectory: dirname(fileURLToPath(import.meta.url)) });

export default [
  ...compat.extends("next/core-web-vitals", "next/typescript"),
  {
    // Job and model text is untrusted: it is only ever rendered as React text.
    rules: { "no-restricted-syntax": ["error", { selector: "JSXAttribute[name.name='dangerouslySetInnerHTML']", message: "Never inject HTML." }] },
  },
  // Links to the classic pages are served by Django, not by this app's router, so plain <a> is right.
  { rules: { "@next/next/no-html-link-for-pages": "off" } },
  { ignores: [".next/**", "out/**"] },
];
