import { render, screen } from 'test/layout-test-utils';
import General from '../General';

describe('General settings — UI mode selector', () => {
  beforeEach(() => localStorage.clear());

  it('renders the Interface selector defaulting to Basic', () => {
    render(<General />);
    expect(screen.getByText('Interface')).toBeInTheDocument();
    expect(screen.getByTestId('ui-mode-selector')).toHaveTextContent('Basic');
  });
});
