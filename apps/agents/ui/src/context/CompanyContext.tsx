import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import type { Company } from "@paperclipai/shared";
import { accessApi } from "../api/access";
import { companiesApi } from "../api/companies";
import { companiesListQueryOptions, type CompanyListResult } from "../api/companies-query";
import { queryKeys } from "../lib/queryKeys";
import type { CompanySelectionSource } from "../lib/company-selection";
type CompanySelectionOptions = { source?: CompanySelectionSource };

interface CompanyContextValue {
  companies: Company[];
  selectedCompanyId: string | null;
  selectedCompany: Company | null;
  selectionSource: CompanySelectionSource;
  loading: boolean;
  error: Error | null;
  setSelectedCompanyId: (companyId: string, options?: CompanySelectionOptions) => void;
  reloadCompanies: () => Promise<void>;
  createCompany: (data: {
    name: string;
    description?: string | null;
    budgetMonthlyCents?: number;
  }) => Promise<Company>;
}

const STORAGE_KEY = "paperclip.selectedCompanyId";

const CompanyContext = createContext<CompanyContextValue | null>(null);

export function resolveBootstrapCompanySelection(input: {
  companies: Array<Pick<Company, "id">>;
  sidebarCompanies: Array<Pick<Company, "id">>;
  selectedCompanyId: string | null;
  storedCompanyId: string | null;
  /**
   * The companies this user can actually work in, or undefined while that is
   * still loading.
   *
   * `GET /companies` returns every company to an instance admin, but
   * `hasCompanyAccess` — which guards every other company route — requires
   * membership and deliberately gives instance admins no blanket access. So the
   * list can contain companies whose every request will 403, and landing on one
   * leaves the app on a wall of loading skeletons with no visible way out: the
   * dashboard, agents, issues, projects and routines all refused, and the
   * company cannot even be left by deleting it, because delete checks the same
   * access. Observed exactly that way on the live instance.
   *
   * Undefined means "not known yet", which must not be read as "no access" —
   * that would blank the app on every cold start.
   */
  accessibleCompanyIds?: string[];
}) {
  if (input.companies.length === 0) return null;

  const listed = input.sidebarCompanies.length > 0
    ? input.sidebarCompanies
    : input.companies;

  // Narrow to what the user can use, but only when that narrowing leaves
  // something. A user who is a member of nothing gets the old behaviour rather
  // than a blank screen: every request refuses either way, and picking one at
  // least leaves the company switcher reachable.
  const accessible = input.accessibleCompanyIds;
  const usable = accessible
    ? listed.filter((company) => accessible.includes(company.id))
    : listed;
  const selectableCompanies = usable.length > 0 ? usable : listed;
  if (input.selectedCompanyId && selectableCompanies.some((company) => company.id === input.selectedCompanyId)) {
    return input.selectedCompanyId;
  }
  if (input.storedCompanyId && selectableCompanies.some((company) => company.id === input.storedCompanyId)) {
    return input.storedCompanyId;
  }
  return selectableCompanies[0]?.id ?? null;
}

export function shouldClearStoredCompanySelection(input: {
  companies: Array<Pick<Company, "id">>;
  isLoading: boolean;
  unauthorized: boolean;
}) {
  return !input.isLoading && !input.unauthorized && input.companies.length === 0;
}

export function CompanyProvider({ children }: { children: ReactNode }) {
  const queryClient = useQueryClient();
  const [selectionSource, setSelectionSource] = useState<CompanySelectionSource>("bootstrap");
  const [selectedCompanyId, setSelectedCompanyIdState] = useState<string | null>(null);

  const { data: companiesResult = { companies: [], unauthorized: false }, isLoading, error } =
    useQuery<CompanyListResult>(companiesListQueryOptions);
  const companies = companiesResult.companies;
  const companyListUnauthorized = companiesResult.unauthorized;
  /**
   * Which of those companies this user can actually work in.
   *
   * Read-only, cached alongside the same key `CloudAccessGate` already uses, so
   * this adds no request of its own. `undefined` while it loads, which
   * `resolveBootstrapCompanySelection` treats as "not known yet" rather than
   * "no access".
   */
  const { data: boardAccess } = useQuery({
    queryKey: queryKeys.access.currentBoardAccess,
    queryFn: () => accessApi.getCurrentBoardAccess(),
    retry: false,
    staleTime: 60_000,
  });

  const sidebarCompanies = useMemo(
    () => companies.filter((company) => company.status !== "archived"),
    [companies],
  );

  // Auto-select first company when list loads
  useEffect(() => {
    if (isLoading) return;
    if (companies.length === 0) {
      if (shouldClearStoredCompanySelection({ companies, isLoading: false, unauthorized: companyListUnauthorized })) {
        if (selectedCompanyId !== null) {
          setSelectedCompanyIdState(null);
        }
        localStorage.removeItem(STORAGE_KEY);
      }
      return;
    }

    const next = resolveBootstrapCompanySelection({
      companies,
      sidebarCompanies,
      selectedCompanyId,
      storedCompanyId: localStorage.getItem(STORAGE_KEY),
      accessibleCompanyIds: boardAccess?.companyIds,
    });
    if (next === null || next === selectedCompanyId) return;
    setSelectedCompanyIdState(next);
    setSelectionSource("bootstrap");
    localStorage.setItem(STORAGE_KEY, next);
  }, [boardAccess?.companyIds, companies, companyListUnauthorized, isLoading, selectedCompanyId, sidebarCompanies]);

  const setSelectedCompanyId = useCallback((companyId: string, options?: CompanySelectionOptions) => {
    setSelectedCompanyIdState(companyId);
    setSelectionSource(options?.source ?? "manual");
    localStorage.setItem(STORAGE_KEY, companyId);
  }, []);

  const reloadCompanies = useCallback(async () => {
    await queryClient.invalidateQueries({ queryKey: queryKeys.companies.all });
  }, [queryClient]);

  const createMutation = useMutation({
    mutationFn: (data: {
      name: string;
      description?: string | null;
      budgetMonthlyCents?: number;
    }) =>
      companiesApi.create(data),
    onSuccess: (company) => {
      queryClient.invalidateQueries({ queryKey: queryKeys.companies.all });
      setSelectedCompanyId(company.id);
    },
  });

  const createCompany = useCallback(
    async (data: {
      name: string;
      description?: string | null;
      budgetMonthlyCents?: number;
    }) => {
      return createMutation.mutateAsync(data);
    },
    [createMutation],
  );

  const selectedCompany = useMemo(
    () => companies.find((company) => company.id === selectedCompanyId) ?? null,
    [companies, selectedCompanyId],
  );

  const value = useMemo(
    () => ({
      companies,
      selectedCompanyId,
      selectedCompany,
      selectionSource,
      loading: isLoading,
      error: error as Error | null,
      setSelectedCompanyId,
      reloadCompanies,
      createCompany,
    }),
    [
      companies,
      selectedCompanyId,
      selectedCompany,
      selectionSource,
      isLoading,
      error,
      setSelectedCompanyId,
      reloadCompanies,
      createCompany,
    ],
  );

  return <CompanyContext.Provider value={value}>{children}</CompanyContext.Provider>;
}

export function useCompany() {
  const ctx = useContext(CompanyContext);
  if (!ctx) {
    throw new Error("useCompany must be used within CompanyProvider");
  }
  return ctx;
}

/**
 * Non-throwing variant of {@link useCompany}. Returns null when called outside a
 * CompanyProvider instead of throwing, so components that may render in
 * provider-less surfaces (e.g. exported/standalone markdown) can read company
 * state without crashing.
 */
export function useOptionalCompany(): CompanyContextValue | null {
  return useContext(CompanyContext);
}
