import { fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter, useNavigate } from "react-router-dom";
import HelpDropdown from "../HelpDropdown";

jest.mock("@/components/ui/button", () => ({
  Button: ({ children, ...props }: any) => (
    <button {...props}>{children}</button>
  ),
}));

jest.mock("@/components/ui/dropdown-menu", () => ({
  DropdownMenu: ({ children, ...props }: any) => (
    <div data-testid="dropdown-menu" {...props}>
      {children}
    </div>
  ),
  DropdownMenuTrigger: ({ children, ...props }: any) => (
    <div data-testid="dropdown-trigger" {...props}>
      {children}
    </div>
  ),
  DropdownMenuContent: ({ children, ...props }: any) => (
    <div data-testid="dropdown-content" {...props}>
      {children}
    </div>
  ),
}));

jest.mock("@/components/common/genericIconComponent", () => ({
  __esModule: true,
  default: () => <span data-testid="icon" />,
  ForwardedIconComponent: ({ name }: { name: string }) => (
    <span data-testid={`icon-${name}`} />
  ),
}));

// NuFi: HelpDropdown.tsx no longer sources its Docs link from
// constants/constants.ts (DOCS_URL/DATASTAX_DOCS_URL, both upstream
// langflow.org domains) -- it uses customization/utils/urls.ts's
// NUFI_DOCS_URL instead. BUG_REPORT_URL/DESKTOP_URL are gone entirely
// along with the menu items that used them. See HelpDropdown.tsx's header
// comment for the full reasoning.
jest.mock("@/customization/utils/urls", () => ({
  __esModule: true,
  NUFI_DOCS_URL: "https://docs.app.nufi.me",
}));

jest.mock("@/utils/utils", () => ({
  cn: (...args: any[]) => args.filter(Boolean).join(" "),
  getOS: () => "macos",
}));

jest.mock("react-router-dom", () => {
  const actual = jest.requireActual("react-router-dom");
  return {
    ...actual,
    useNavigate: jest.fn(),
  };
});

jest.mock("@/stores/darkStore", () => ({
  useDarkStore: () => ({
    dark: false,
    setDark: jest.fn(),
  }),
}));

jest.mock("@/stores/flowStore", () => ({
  __esModule: true,
  default: () => ({
    helperLineEnabled: false,
    setHelperLineEnabled: jest.fn(),
  }),
}));

// Mock window.open
Object.defineProperty(window, "open", {
  writable: true,
  value: jest.fn(),
});

describe("HelpDropdown", () => {
  beforeEach(() => {
    (window.open as jest.Mock).mockClear();
  });

  it("opens docs in new tab and navigates to shortcuts", () => {
    const mockNavigate = jest.fn();
    (useNavigate as unknown as jest.Mock).mockReturnValue(mockNavigate);

    render(
      <MemoryRouter>
        <HelpDropdown isOpen={true} onOpenChange={() => {}} />
      </MemoryRouter>,
    );

    fireEvent.click(screen.getByTestId("canvas_controls_dropdown_docs"));
    expect(window.open).toHaveBeenCalledWith(
      "https://docs.app.nufi.me",
      "_blank",
    );

    fireEvent.click(screen.getByTestId("canvas_controls_dropdown_shortcuts"));
    expect(mockNavigate).toHaveBeenCalledWith("/settings/shortcuts");
  });
});
