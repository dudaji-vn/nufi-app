/**
 * Types for rebrand.mjs. The implementation is plain ESM so a Node script can
 * run it directly over server/dist without a build step; these declarations are
 * what let ui/nufi-rebrand.ts import it under `tsc -b`.
 */

export declare const BRAND: string;
export declare const PRODUCT: string;

/** Rewrites text the client renders. Safe to apply to one side alone. */
export declare function rebrandRenderedProps(code: string): string;

/** Rewrites every string literal. Safe only when both bundles get it. */
export declare function rebrandAll(code: string): string;
