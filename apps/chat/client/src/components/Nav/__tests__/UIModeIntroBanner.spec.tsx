import { render, screen, fireEvent } from '@testing-library/react';
import { RecoilRoot } from 'recoil';
import { useUIMode } from '~/hooks';
import UIModeIntroBanner from '../UIModeIntroBanner';

function renderWithProviders(ui: React.ReactElement) {
  return render(<RecoilRoot>{ui}</RecoilRoot>);
}

function ModeSwitcher() {
  const { setMode } = useUIMode();
  return (
    <button type="button" data-testid="go-advanced" onClick={() => setMode('advanced')}>
      advanced
    </button>
  );
}

describe('UIModeIntroBanner', () => {
  beforeEach(() => localStorage.clear());

  it('shows once for a default (basic) user and hides after dismiss', () => {
    const { rerender } = renderWithProviders(<UIModeIntroBanner />);
    expect(screen.getByRole('status')).toBeInTheDocument();

    fireEvent.click(screen.getByTestId('ui-mode-intro-dismiss'));
    expect(localStorage.getItem('uiModeIntroSeen')).toBe(JSON.stringify(true));

    rerender(
      <RecoilRoot>
        <UIModeIntroBanner />
      </RecoilRoot>,
    );
    expect(screen.queryByRole('status')).not.toBeInTheDocument();
  });

  it('does not show if already seen', () => {
    localStorage.setItem('uiModeIntroSeen', JSON.stringify(true));
    renderWithProviders(<UIModeIntroBanner />);
    expect(screen.queryByRole('status')).not.toBeInTheDocument();
  });

  it('references both intro banner and dismiss locale keys', () => {
    renderWithProviders(<UIModeIntroBanner />);
    expect(screen.getByTestId('ui-mode-intro-dismiss')).toBeInTheDocument();
    expect(screen.getByRole('status').textContent).toBeTruthy();
  });

  it('reports its rendered height and resets to 0 on dismiss', () => {
    const onHeightChange = jest.fn();
    renderWithProviders(<UIModeIntroBanner onHeightChange={onHeightChange} />);

    expect(onHeightChange).toHaveBeenCalledWith(expect.any(Number));
    onHeightChange.mockClear();

    fireEvent.click(screen.getByTestId('ui-mode-intro-dismiss'));
    expect(onHeightChange).toHaveBeenCalledWith(0);
  });

  it('reports a height of 0 when already seen', () => {
    localStorage.setItem('uiModeIntroSeen', JSON.stringify(true));
    const onHeightChange = jest.fn();
    renderWithProviders(<UIModeIntroBanner onHeightChange={onHeightChange} />);

    expect(onHeightChange).toHaveBeenCalledWith(0);
  });

  it('does not show in advanced mode even if not yet seen', () => {
    localStorage.setItem('uiMode', JSON.stringify('advanced'));
    const onHeightChange = jest.fn();
    renderWithProviders(<UIModeIntroBanner onHeightChange={onHeightChange} />);

    expect(screen.queryByRole('status')).not.toBeInTheDocument();
    expect(onHeightChange).toHaveBeenCalledWith(0);
  });

  it('hides live when the user switches to advanced', () => {
    renderWithProviders(
      <>
        <UIModeIntroBanner />
        <ModeSwitcher />
      </>,
    );
    expect(screen.getByRole('status')).toBeInTheDocument();

    fireEvent.click(screen.getByTestId('go-advanced'));
    expect(screen.queryByRole('status')).not.toBeInTheDocument();
  });
});
