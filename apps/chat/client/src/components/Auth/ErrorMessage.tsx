export const ErrorMessage = ({ children }: { children: React.ReactNode }) => (
  <div
    role="alert"
    aria-live="assertive"
    className="relative mt-6 rounded-xl border border-destructive/30 bg-destructive/10 px-6 py-4 text-destructive shadow-sm transition-all"
  >
    {children}
  </div>
);
