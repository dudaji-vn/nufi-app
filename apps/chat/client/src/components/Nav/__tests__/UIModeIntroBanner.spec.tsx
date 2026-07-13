import { render, screen, fireEvent } from '@testing-library/react';
import { RecoilRoot } from 'recoil';
import UIModeIntroBanner from '../UIModeIntroBanner';

function renderWithProviders(ui: React.ReactElement) {
  return render(<RecoilRoot>{ui}</RecoilRoot>);
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
});
