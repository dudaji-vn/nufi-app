import { useCallback, useState } from "react";
import { useNavigate } from "react-router-dom";
import { HelpDropdownView } from "@/components/core/canvasControlsComponent/HelpDropdownView";
import { NUFI_DOCS_URL } from "@/customization/utils/urls";
import useFlowStore from "@/stores/flowStore";

// NuFi: this is a core file, not a customization/ override -- upstream
// never built a seam here, unlike appHeaderComponent's AccountMenu (see
// customization/components/custom-AccountMenu.tsx's header comment for
// that seam's version of the same fix). Found in the same sweep that
// fixed the account menu: this dropdown (the canvas toolbar's "?" button)
// previously wired BUG_REPORT_URL (github.com/langflow-ai/langflow/issues)
// and DESKTOP_URL (langflow.org/desktop -- literally advertising a
// competitor's desktop app) from constants/constants.ts, plus a Docs link
// that resolved to docs.langflow.org with ENABLE_DATASTAX_LANGFLOW false.
// Both third-party links are dropped; Docs is kept but repointed at
// NUFI_DOCS_URL (customization/utils/urls.ts -- the same NuFi docs domain
// the account menu now uses), not deleted, per the same "don't regress a
// legitimate item into uselessness" reasoning applied there. Since there's
// no seam to override, this edit lives directly in the core file, allow-
// listed in check-fork-diff.sh per its own guidance (option 3: "if it
// genuinely must live here, add the path to ALLOWLIST ... and say why").
// See nufi/README.md "Third-party brand/link sweep" for the rest of this
// sweep's results.
const HelpDropdown = () => {
  const navigate = useNavigate();
  const [isHelpMenuOpen, setIsHelpMenuOpen] = useState(false);
  const helperLineEnabled = useFlowStore((state) => state.helperLineEnabled);
  const setHelperLineEnabled = useFlowStore(
    (state) => state.setHelperLineEnabled,
  );

  const onToggleHelperLines = useCallback(() => {
    setHelperLineEnabled(!helperLineEnabled);
  }, [helperLineEnabled]);

  return (
    <HelpDropdownView
      isOpen={isHelpMenuOpen}
      onOpenChange={setIsHelpMenuOpen}
      helperLineEnabled={helperLineEnabled}
      onToggleHelperLines={onToggleHelperLines}
      navigateTo={(path) => navigate(path)}
      openLink={(url) => window.open(url, "_blank")}
      urls={{ docs: NUFI_DOCS_URL }}
    />
  );
};

export default HelpDropdown;
