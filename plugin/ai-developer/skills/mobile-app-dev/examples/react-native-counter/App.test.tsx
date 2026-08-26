// App.test.tsx -- run with `npm test`.

import React from 'react';
import { render, fireEvent } from '@testing-library/react-native';
import App from './App';

describe('Counter', () => {
  it('renders initial count', () => {
    const { getByText } = render(<App />);
    expect(getByText('0')).toBeTruthy();
  });

  it('increments on button press', () => {
    const { getByText } = render(<App />);
    fireEvent.press(getByText('Increment'));
    expect(getByText('1')).toBeTruthy();
  });
});