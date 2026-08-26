import { useTranslation } from "react-i18next";
import logoDarkPng from "@/assets/logo_dark.png";
import logoLightPng from "@/assets/logo_light.png";
import { ForwardedIconComponent } from "@/components/common/genericIconComponent";
import CardsWrapComponent from "@/components/core/cardsWrapComponent";
import { useStartNewFlow } from "@/components/core/flowBuilderWelcome/hooks/use-start-new-flow";
import { Button } from "@/components/ui/button";
import { DotBackgroundDemo } from "@/components/ui/dot-background";
import useFileDrop from "@/pages/MainPage/hooks/use-on-file-drop";
import { useFolderStore } from "@/stores/foldersStore";

/**
 * NuFi-authored replacement for `pages/MainPage/pages/empty-page.tsx`'s
 * `EmptyPageCommunity`, not a pass-through to it.
 *
 * Upstream's empty state renders two large cards below the welcome copy: a
 * live GitHub star count linking to github.com/langflow-ai/langflow, and a
 * live Discord member count linking to Langflow's own Discord invite (both
 * fetched via useDarkStore -- see stores/darkStore.ts -- the same widget
 * the header drops in custom-langflow-counts.tsx). It's the first screen a
 * fresh install shows, so those two cards are the highest-visibility
 * instance of "NUFI Studio" advertising the upstream project it was forked
 * from -- worse than the header badge, since these are full click targets
 * with descriptive copy, not a passive counter.
 *
 * `pages/MainPage/pages/empty-page.tsx` has no prop or seam to suppress
 * just those two cards -- upstream didn't build one, unlike the header's
 * dedicated CustomLangflowCounts override point. The two options were: (a)
 * add empty-page.tsx to check-fork-diff.sh's allowlist and edit it
 * directly, or (b) stop delegating to it from this seam and own the
 * layout here instead. (b) was chosen: this file (`customization/`) is
 * already the place a fork is *expected* to diverge -- check-fork-diff.sh
 * exists precisely so `apps/nufi-agent`'s other ~8,900 files don't have
 * to, and every edit inside `customization/` is exactly the kind of
 * change `git subtree pull` was designed to leave alone. Editing
 * empty-page.tsx directly would instead put a second, unrelated-looking
 * diff onto a file upstream actively changes, growing the surface a
 * resync has to reconcile for no benefit over doing it here.
 *
 * The real trade, stated plainly: this component now owns its own copy of
 * the empty-state layout (logo, welcome copy, drag-and-drop wrapper,
 * "create first flow" button) instead of inheriting upstream's future
 * changes to `EmptyPageCommunity` automatically. For a small, purely
 * presentational leaf page like this one, that's the right side of the
 * trade -- a `git subtree pull` that reshapes this screen shows up as
 * silence here (this file keeps working, just stops picking up the new
 * look) rather than as a merge conflict on a file with someone else's
 * edits in it. See nufi/README.md "Third-party brand/link sweep" for the
 * rest of the customization-seam sweep this came out of.
 */
export const CustomEmptyPageCommunity = ({
  setOpenModal: _setOpenModal,
}: {
  setOpenModal: (open: boolean) => void;
}) => {
  const { t } = useTranslation();
  const handleFileDrop = useFileDrop(undefined);
  const folders = useFolderStore((state) => state.folders);
  const startNewFlow = useStartNewFlow();

  return (
    <DotBackgroundDemo>
      <CardsWrapComponent
        dragMessage={t("home.dragFlowsOrComponents")}
        onFileDrop={handleFileDrop}
      >
        <div className="m-0 h-full w-full bg-background p-0">
          <div className="z-50 flex h-full w-full flex-col items-center justify-center gap-5">
            <div className="z-50 flex flex-col items-center gap-2">
              <div className="z-50 dark:hidden">
                <img
                  src={logoLightPng}
                  alt={t("common.langflowLogoLight")}
                  data-testid="empty_page_logo_light"
                  className="relative top-8 h-40 pointer-events-none select-none"
                />
              </div>
              <div className="z-50 hidden dark:block">
                <img
                  src={logoDarkPng}
                  alt={t("common.langflowLogoDark")}
                  data-testid="empty_page_logo_dark"
                  className="relative top-8 h-40 pointer-events-none select-none"
                />
              </div>
              <span
                data-testid="mainpage_title"
                className="z-50 text-center font-chivo text-2xl font-medium text-foreground"
              >
                {t("page.welcomeTitle")}
              </span>

              <span
                data-testid="empty_page_description"
                className="z-50 text-center text-base text-secondary-foreground"
              >
                {folders?.length > 1
                  ? t("page.emptyFolder")
                  : t("page.welcomeDescription")}
              </span>
            </div>

            <div className="flex w-full max-w-[510px] flex-col gap-7 sm:gap-[29px]">
              <Button
                variant="default"
                className="z-10 m-auto mt-3 h-auto min-h-10 w-auto whitespace-normal rounded-lg font-bold transition-all duration-300"
                onClick={() => startNewFlow()}
                id="new-project-btn"
                data-testid="new_project_btn_empty_page"
              >
                <ForwardedIconComponent
                  name="Plus"
                  aria-hidden="true"
                  className="h-4 w-4"
                />
                <span>{t("page.createFirstFlow")}</span>
              </Button>
            </div>
          </div>
        </div>
        <p
          data-testid="empty_page_drag_and_drop_text"
          className="absolute bottom-5 left-0 right-0 mt-4 cursor-default text-center text-xxs text-muted-foreground"
        >
          {t("page.dragAndDropText")}
        </p>
      </CardsWrapComponent>
    </DotBackgroundDemo>
  );
};

export default CustomEmptyPageCommunity;
