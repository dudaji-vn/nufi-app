import { useTranslation } from "react-i18next";
import {
  HeaderMenu,
  HeaderMenuItemButton,
  HeaderMenuItemLink,
  HeaderMenuItems,
  HeaderMenuToggle,
} from "@/components/core/appHeaderComponent/components/HeaderMenu";
import { ThemeButtons } from "@/components/core/appHeaderComponent/components/ThemeButtons";
import { useLogout } from "@/controllers/API/queries/auth";
import { CustomProfileIcon } from "@/customization/components/custom-profile-icon";
import { useCustomNavigate } from "@/customization/hooks/use-custom-navigate";
import { NUFI_DOCS_URL } from "@/customization/utils/urls";
import useAuthStore from "@/stores/authStore";
import { useDarkStore } from "@/stores/darkStore";
import { useUtilityStore } from "@/stores/utilityStore";
import { cn, stripReleaseStageFromVersion } from "@/utils/utils";

/**
 * NuFi-authored replacement for
 * components/core/appHeaderComponent/components/AccountMenu/index.tsx's
 * AccountMenu, not a pass-through to it -- same class of bug, same fix
 * shape, as custom-empty-page.tsx (C1).
 *
 * Upstream's user-menu dropdown (the header's account icon) renders three
 * live third-party links below Settings/the admin link: GitHub
 * (github.com/langflow-ai/langflow), Discord (Langflow's own invite server)
 * and X/Twitter (x.com/langflow_ai) -- plus a Docs link that, with
 * ENABLE_DATASTAX_LANGFLOW hardcoded false (customization/feature-flags.ts),
 * resolves to docs.langflow.org. All four sit behind a click on the header's
 * profile icon -- exactly the "brand link behind UI state" shape this fork
 * has now shipped twice (see custom-empty-page.tsx's header comment for the
 * first instance): no grep of what's on screen at mount, and no read of
 * `appHeaderComponent/index.tsx` alone, surfaces a dropdown's own contents.
 *
 * `AccountMenu/index.tsx` has no prop or seam to drop just those four items
 * -- same situation custom-empty-page.tsx describes for
 * `EmptyPageCommunity`. This component owns its own copy of the menu
 * instead of delegating, for the same reasons laid out there (keeps the
 * core file byte-identical to upstream so no allowlist entry is needed for
 * it, and keeps a `git subtree pull`'s conflict surface to this
 * already-diverged customization/ file only).
 *
 * Kept, unchanged from upstream: Version, Settings, the admin-page link
 * (isAdmin && !autoLogin), Theme (light/dark/system via ThemeButtons), and
 * Logout (!autoLogin && !hideLogoutButton). Removing the brand links while
 * also removing the menu's actual utility would trade the original defect
 * for a worse one -- flagged explicitly in this task's brief.
 *
 * Docs: NOT dropped, the other option the task allowed. NuFi has its own
 * public docs site -- apps/docs in this monorepo, deployed as the
 * `nufi-docs` Railway service with custom domain docs.app.nufi.me (Railway
 * domain list: ACTIVE; also curl-verified live, HTTP 200). Repointed there
 * via customization/utils/urls.ts's NUFI_DOCS_URL instead of upstream's
 * DOCS_URL/DATASTAX_DOCS_URL, so the same constant backs every Docs-link
 * seam this sweep touched -- see
 * components/core/canvasControlsComponent/HelpDropdown.tsx, fixed in the
 * same change for the identical GitHub/marketing-link bug behind the
 * canvas Help dropdown.
 *
 * See nufi/README.md "Third-party brand/link sweep" for the rest of this
 * sweep's results (the account-menu round).
 */
export const CustomAccountMenu = () => {
  const { t } = useTranslation();
  const version = useDarkStore((state) => state.version);
  const latestVersion = useDarkStore((state) => state.latestVersion);
  const navigate = useCustomNavigate();
  const { mutate: mutationLogout } = useLogout();
  const hideLogoutButton = useUtilityStore((state) => state.hideLogoutButton);

  const { isAdmin, autoLogin } = useAuthStore((state) => ({
    isAdmin: state.isAdmin,
    autoLogin: state.autoLogin,
  }));

  const handleLogout = () => {
    mutationLogout();
  };

  const isLatestVersion = (() => {
    if (!version || !latestVersion) return false;

    const currentBaseVersion = stripReleaseStageFromVersion(version);
    const latestBaseVersion = stripReleaseStageFromVersion(latestVersion);

    return currentBaseVersion === latestBaseVersion;
  })();

  return (
    <HeaderMenu>
      <HeaderMenuToggle>
        <div
          className="h-6 w-6 rounded-lg focus-visible:outline-0"
          data-testid="user-profile-settings"
        >
          <CustomProfileIcon />
        </div>
      </HeaderMenuToggle>
      <HeaderMenuItems position="right" classNameSize="w-[272px]">
        <div className="divide-y divide-foreground/10">
          <div>
            <div className="h-[44px] items-center px-4 pt-3">
              <div className="flex items-center justify-between">
                <span
                  data-testid="menu_version_button"
                  id="menu_version_button"
                  className="text-sm"
                >
                  {t("account.version")}
                </span>
                <div
                  className={cn(
                    "float-right text-xs",
                    isLatestVersion && "text-accent-emerald-foreground",
                    !isLatestVersion && "text-accent-amber-foreground",
                  )}
                >
                  {version}{" "}
                  {isLatestVersion
                    ? t("account.latest")
                    : t("account.updateAvailable")}
                </div>
              </div>
            </div>
          </div>

          <div>
            <HeaderMenuItemButton
              onClick={() => {
                navigate("/settings");
              }}
            >
              <span
                data-testid="menu_settings_button"
                id="menu_settings_button"
              >
                {t("account.settings")}
              </span>
            </HeaderMenuItemButton>

            {isAdmin && !autoLogin && (
              <div>
                <HeaderMenuItemButton
                  onClick={() => {
                    navigate("/admin");
                  }}
                >
                  <span
                    data-testid="menu_admin_page_button"
                    id="menu_admin_page_button"
                  >
                    {t("account.adminPage")}
                  </span>
                </HeaderMenuItemButton>
              </div>
            )}
            <HeaderMenuItemLink newPage href={NUFI_DOCS_URL}>
              <span data-testid="menu_docs_button" id="menu_docs_button">
                {t("account.docs")}
              </span>
            </HeaderMenuItemLink>
          </div>

          <div className="flex items-center justify-between px-4 py-[6.5px] text-sm">
            <span className="">{t("account.theme")}</span>
            <div className="relative top-[1px] float-right">
              <ThemeButtons />
            </div>
          </div>

          {!autoLogin && !hideLogoutButton && (
            <div>
              <HeaderMenuItemButton onClick={handleLogout} icon="log-out">
                {t("account.logout")}
              </HeaderMenuItemButton>
            </div>
          )}
        </div>
      </HeaderMenuItems>
    </HeaderMenu>
  );
};

export default CustomAccountMenu;
