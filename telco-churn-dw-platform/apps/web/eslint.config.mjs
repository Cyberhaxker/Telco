import { dirname } from "node:path";
import { fileURLToPath } from "node:url";
import { FlatCompat } from "@eslint/eslintrc";

const compat = new FlatCompat({ baseDirectory: dirname(fileURLToPath(import.meta.url)) });

export default [
  { ignores: ["out/**", ".next/**", "public/sw.js", "src/contracts/**", "src/lib/generated/**"] },
  ...compat.extends("next/core-web-vitals", "next/typescript"),
];
