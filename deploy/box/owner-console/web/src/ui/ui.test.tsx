import { act, cleanup, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, expect, test, vi } from 'vitest';
import { Badge } from './badge';
import { Button } from './button';
import { Avatar } from './avatar';
import { Card } from './card';
import { Checkbox } from './checkbox';
import { ContextMenu } from './context-menu';
import { Input } from './input';
import { Radio } from './radio';
import { Select } from './select';
import { Modal } from './modal';
import { Table } from './table';
import { Tabs } from './tabs';
import { Toaster, useToast } from './toast';

afterEach(cleanup);

test('Button renders label and variant class', () => {
  render(<Button variant="danger">Stop</Button>);
  const b = screen.getByRole('button', { name: 'Stop' });
  expect(b.className).toContain('danger');
});

test('Button defaults to primary and forwards props', () => {
  const onClick = vi.fn();
  render(<Button onClick={onClick}>Go</Button>);
  const b = screen.getByRole('button', { name: 'Go' });
  expect(b.className).toContain('primary');
  fireEvent.click(b);
  expect(onClick).toHaveBeenCalled();
});

test('Badge ok tone', () => {
  render(<Badge tone="ok">Running</Badge>);
  expect(screen.getByText('Running').className).toContain('ok');
});

test('Card shows title and right slot', () => {
  render(
    <Card title="Service" right={<span>RIGHT</span>}>
      body
    </Card>,
  );
  expect(screen.getByText('Service')).toBeTruthy();
  expect(screen.getByText('RIGHT')).toBeTruthy();
  expect(screen.getByText('body')).toBeTruthy();
});

test('Tabs marks active and calls onChange', () => {
  const onChange = vi.fn();
  render(
    <Tabs
      tabs={[
        { id: 'general', label: 'General' },
        { id: 'users', label: 'Users' },
      ]}
      active="general"
      onChange={onChange}
    />,
  );
  expect(screen.getByRole('tab', { name: 'General' }).getAttribute('aria-selected')).toBe('true');
  expect(screen.getByRole('tab', { name: 'Users' }).getAttribute('aria-selected')).toBe('false');
  fireEvent.click(screen.getByRole('tab', { name: 'Users' }));
  expect(onChange).toHaveBeenCalledWith('users');
});

test('Table renders headers, rows and custom render', () => {
  render(
    <Table
      columns={[
        { key: 'name', label: 'Name' },
        { key: 'role', label: 'Role', render: (r) => <b>{String(r.role).toUpperCase()}</b> },
      ]}
      rows={[{ name: 'Ann', role: 'admin' }]}
    />,
  );
  expect(screen.getByRole('columnheader', { name: 'Name' })).toBeTruthy();
  expect(screen.getByRole('cell', { name: 'Ann' })).toBeTruthy();
  expect(screen.getByText('ADMIN')).toBeTruthy();
});

test('Table shows empty message', () => {
  render(<Table columns={[{ key: 'a', label: 'A' }]} rows={[]} empty="Nothing here" />);
  expect(screen.getByText('Nothing here')).toBeTruthy();
});

test('Modal renders only when open, with actions and close', () => {
  const onClose = vi.fn();
  const { rerender } = render(
    <Modal open={false} title="Restart Service?" onClose={onClose} actions={<button>Do</button>}>
      sure?
    </Modal>,
  );
  expect(screen.queryByRole('dialog')).toBeNull();
  rerender(
    <Modal open title="Restart Service?" onClose={onClose} actions={<button>Do</button>}>
      sure?
    </Modal>,
  );
  expect(screen.getByRole('dialog', { name: 'Restart Service?' })).toBeTruthy();
  expect(screen.getByText('sure?')).toBeTruthy();
  expect(screen.getByRole('button', { name: 'Do' })).toBeTruthy();
  fireEvent.click(screen.getByRole('button', { name: 'Close' }));
  expect(onClose).toHaveBeenCalled();
});

test('Toast push shows a message', () => {
  function Probe() {
    const { push } = useToast();
    return <button onClick={() => push('Saved', 'ok')}>fire</button>;
  }
  render(
    <>
      <Probe />
      <Toaster />
    </>,
  );
  act(() => {
    fireEvent.click(screen.getByText('fire'));
  });
  const t = screen.getByText('Saved');
  expect(t.closest('[role="status"]')).toBeTruthy();
});

test('ContextMenu opens, selects and closes', () => {
  const onSelect = vi.fn();
  render(
    <ContextMenu items={[{ label: 'Rename', onSelect }]}>
      <button type="button">more</button>
    </ContextMenu>,
  );
  expect(screen.queryByRole('menuitem', { name: 'Rename' })).toBeNull();
  fireEvent.click(screen.getByRole('button', { name: 'more' }));
  fireEvent.click(screen.getByRole('menuitem', { name: 'Rename' }));
  expect(onSelect).toHaveBeenCalledTimes(1);
  expect(screen.queryByRole('menuitem', { name: 'Rename' })).toBeNull();
});

test('ContextMenu disabled item does not fire; Escape and outside click close', () => {
  const onSelect = vi.fn();
  render(
    <div>
      <ContextMenu items={[{ label: 'Delete', danger: true, disabled: true, onSelect }]}>
        <button type="button">more</button>
      </ContextMenu>
      <p>outside</p>
    </div>,
  );
  fireEvent.click(screen.getByRole('button', { name: 'more' }));
  fireEvent.click(screen.getByRole('menuitem', { name: 'Delete' }));
  expect(onSelect).not.toHaveBeenCalled();
  expect(screen.getByRole('menuitem', { name: 'Delete' })).toBeTruthy();
  fireEvent.keyDown(window, { key: 'Escape' });
  expect(screen.queryByRole('menu')).toBeNull();
  fireEvent.click(screen.getByRole('button', { name: 'more' }));
  fireEvent.mouseDown(screen.getByText('outside'));
  expect(screen.queryByRole('menu')).toBeNull();
});

test('Radio reflects checked, shows hint, reports value', () => {
  const onChange = vi.fn();
  render(<Radio name="a" value="big" checked label="Big" hint="Larger text" onChange={onChange} />);
  const r = screen.getByRole('radio') as HTMLInputElement;
  expect(r.checked).toBe(true);
  expect(screen.getByText('Big')).toBeTruthy();
  expect(screen.getByText('Larger text')).toBeTruthy();
  cleanup();
  render(<Radio name="a" value="big" checked={false} label="Big" onChange={onChange} />);
  fireEvent.click(screen.getByRole('radio'));
  expect(onChange).toHaveBeenCalledWith('big');
});

test('Checkbox toggles with new boolean', () => {
  const onChange = vi.fn();
  render(<Checkbox checked={false} onChange={onChange} label="All" />);
  fireEvent.click(screen.getByRole('checkbox', { name: 'All' }));
  expect(onChange).toHaveBeenCalledWith(true);
});

test('Select renders options and reports value', () => {
  const onChange = vi.fn();
  render(
    <Select
      value="a"
      onChange={onChange}
      options={[
        { value: 'a', label: 'Alpha' },
        { value: 'b', label: 'Beta' },
      ]}
    />,
  );
  expect(screen.getAllByRole('option')).toHaveLength(2);
  fireEvent.change(screen.getByRole('combobox'), { target: { value: 'b' } });
  expect(onChange).toHaveBeenCalledWith('b');
});

test('Input forwards props', () => {
  const onChange = vi.fn();
  render(<Input value="hi" onChange={onChange} placeholder="Name" />);
  const i = screen.getByPlaceholderText('Name') as HTMLInputElement;
  expect(i.value).toBe('hi');
  fireEvent.change(i, { target: { value: 'yo' } });
  expect(onChange).toHaveBeenCalled();
});

test('Avatar shows first initial', () => {
  render(<Avatar name="sun" />);
  expect(screen.getByText('S')).toBeTruthy();
});
