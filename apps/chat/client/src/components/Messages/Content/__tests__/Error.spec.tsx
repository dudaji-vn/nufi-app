import { render, screen } from '@testing-library/react';
import { RecoilRoot } from 'recoil';
import { ErrorTypes } from 'librechat-data-provider';
import Error from '../Error';

const renderError = (text: string) =>
  render(
    <RecoilRoot>
      <Error text={text} />
    </RecoilRoot>,
  );

const blocked = (risk: string, reference = 'grd_oata7syzkvv33vnxr7jaxhjume') =>
  JSON.stringify({ type: ErrorTypes.GUARDRAIL_BLOCKED, risk, reference });

describe('Error', () => {
  describe('a security-policy refusal', () => {
    it('reads as a policy decision, not a malfunction', () => {
      const { container } = renderError(blocked('LLM01_INJECTION'));

      expect(container.textContent).not.toMatch(/something went wrong/i);
      expect(screen.getByText(/blocked by security policy/i)).toBeInTheDocument();
      expect(
        screen.getByText(/attempt to override the assistant's instructions/i),
      ).toBeInTheDocument();
    });

    it('keeps the reference id visible so it can be quoted to support', () => {
      renderError(blocked('LLM01_INJECTION'));

      expect(screen.getByText('grd_oata7syzkvv33vnxr7jaxhjume')).toBeVisible();
    });

    it('explains a withheld response differently from a refused request', () => {
      const { container } = renderError(blocked('LLM07_SYSTEM_PROMPT_LEAK'));

      expect(container.textContent).toMatch(/disclose the assistant's configuration/i);
      expect(container.textContent).not.toMatch(/something went wrong/i);
    });

    it('explains a failed-closed security check as temporary', () => {
      const { container } = renderError(blocked('GUARDRAIL_UNAVAILABLE'));

      expect(container.textContent).toMatch(/could not run/i);
      expect(container.textContent).toMatch(/temporary/i);
    });

    it('still frames an unrecognised risk code as a policy decision', () => {
      const { container } = renderError(blocked('LLM99_SHIPPED_AHEAD_OF_THE_CLIENT'));

      expect(container.textContent).not.toMatch(/something went wrong/i);
      expect(container.textContent).toMatch(/blocked by a security policy/i);
      expect(container.textContent).toContain('grd_oata7syzkvv33vnxr7jaxhjume');
    });

    it('renders without a reference rather than showing an empty label', () => {
      const { container } = renderError(
        JSON.stringify({ type: ErrorTypes.GUARDRAIL_BLOCKED, risk: 'LLM01_INJECTION' }),
      );

      expect(container.textContent).not.toMatch(/reference/i);
      expect(container.textContent).toMatch(/blocked by security policy/i);
    });
  });

  describe('every other error', () => {
    it.each([
      'connect ECONNREFUSED 127.0.0.1:4000',
      'An error occurred while processing the request',
      'Upstream is on fire.',
    ])('keeps the generic wrapper for %p', (text) => {
      const { container } = renderError(text);

      expect(container.textContent).toMatch(/something went wrong/i);
      expect(container.textContent).toContain(text);
    });

    it('keeps the generic wrapper for a typed error the client does not know', () => {
      const { container } = renderError(JSON.stringify({ type: 'some_unknown_error' }));

      expect(container.textContent).toMatch(/something went wrong/i);
    });
  });
});
