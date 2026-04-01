export function PermissionsUnavailable() {
  return (
    <div role="alert" className="flex flex-1 flex-col items-center justify-center gap-4 p-6">
      <h2 className="text-xl font-semibold text-(--cui-color-title-default)">
        Could not verify permissions
      </h2>
      <p className="max-w-md text-center text-sm text-(--cui-color-text-muted)">
        The permissions service is temporarily unavailable. Please reload the page to try again.
      </p>
      <button
        type="button"
        onClick={() => window.location.reload()}
        className="mt-2 cursor-pointer rounded-lg border border-(--cui-color-stroke-default) bg-transparent px-4 py-2 text-sm font-medium text-(--cui-color-text-default) transition-colors hover:bg-(--cui-color-background-hover)"
      >
        Reload
      </button>
    </div>
  );
}
