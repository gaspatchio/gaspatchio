// SPDX-FileCopyrightText: 2026 Opio Inc.
//
// SPDX-License-Identifier: Apache-2.0

/** The types of `bundle.mjs`, so that the TypeScript tests can import it. */

import type { BuildOptions, Metafile } from "esbuild";

/** One licence file a package ships, as it ships it. */
export interface LicenceFile {
  name: string;
  text: string;
}

/** One third-party package the bundle carries. */
export interface BundledPackage {
  name: string;
  version: string;
  licence: string;
  licenceFiles: LicenceFile[];
  /** The built files it lands in: `viewer.js`, `viewer.css`. */
  outputs: string[];
  /** The package whose own distributed file carries it, or null. */
  via: string | null;
}

/** One font face `fonts.css` inlines. */
export interface FontFace {
  weight: number;
  file: string;
}

/** One font family, with the copyright lines its licence asks to travel. */
export interface FontFamily {
  family: string;
  copyright: string[];
  faces: FontFace[];
}

export declare const bundleOptions: BuildOptions;
export declare const FONT_FAMILIES: FontFamily[];
export declare function bundledPackages(metafile: Metafile, cwd?: string): BundledPackage[];
export declare function licenceExpression(
  packages: readonly BundledPackage[],
  output: string,
): string;
export declare function thirdPartyNotices(
  packages: readonly BundledPackage[],
  families: readonly FontFamily[],
  oflText: string,
): string;
