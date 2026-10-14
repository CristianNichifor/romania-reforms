export declare const SIMULATORS: ReadonlyArray<readonly [string, string, string]>;
export declare const CSP: string;
export declare const CSP_META: string;
export declare const NAV_STYLE: string;
export declare function navHtml(current: string, prefix: string, lang?: 'ro' | 'en'): string;
export declare function applyShell(
  html: string,
  options: { current: string; prefix?: string; csp?: boolean },
): string;
export declare function siteShell(current: string): {
  name: string;
  transformIndexHtml(html: string, ctx: { server?: unknown }): string;
};
