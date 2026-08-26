// __tests__/App.test.tsx
import React from 'react';
import { render, waitFor } from '@testing-library/react-native';
import App, { useFeedStore } from '../App';

describe('App', () => {
  beforeEach(() => {
    useFeedStore.setState({ items: [], isLoading: false, error: null });
  });

  it('renders initial loading state', () => {
    const { getByLabelText } = render(<App />);
    expect(getByLabelText('Loading')).toBeTruthy();
  });

  it('loads items on mount', async () => {
    const { getByText } = render(<App />);
    await waitFor(() => expect(getByText('First')).toBeTruthy(), { timeout: 3000 });
    expect(getByText('Second')).toBeTruthy();
  });
});