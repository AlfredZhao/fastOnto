try {
  const theme = localStorage.getItem('fastonto.theme.v1');
  if (theme === 'dark' || theme === 'light') document.documentElement.dataset.theme = theme;
} catch {
  // Optional, non-sensitive preference only.
}
