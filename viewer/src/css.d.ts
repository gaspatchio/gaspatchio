// SPDX-FileCopyrightText: 2026 Opio Inc.
//
// SPDX-License-Identifier: Apache-2.0

/**
 * What a stylesheet is, to TypeScript.
 *
 * A component imports its styles for one reason: so that the two travel
 * together and the bundler collects the second while it is collecting the
 * first. There is nothing to import — no class-name map, no object — so the
 * declaration says exactly that, and a component that tried to read a name out
 * of a stylesheet would not compile.
 */

declare module "*.css";
