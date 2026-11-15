import React from 'react';
import {createRoot} from 'react-dom/client';

const basePath = new URL(import.meta.env.BASE_URL, window.location.origin).pathname.replace(/\/$/, '');
const pathname = window.location.pathname.replace(/\/$/, '');

if (pathname === `${basePath}/overview`) {
  document.documentElement.dataset.salusOverview = '';
  document.documentElement.lang = 'en';
  document.title = 'Project Salus · To predict is to protect';
  document.querySelector('meta[name="theme-color"]').content = '#041632';
  const description = document.createElement('meta');
  description.name = 'description';
  description.content = 'Project Salus combines astronaut physical and mental health, spacecraft conditions and NASA space weather to anticipate risks and alert the medical team before they become problems.';
  document.head.append(description);
  import('./Overview.jsx').then(({default: Overview}) => {
    createRoot(document.getElementById('root')).render(<Overview/>);
  });
} else {
  import('./main.jsx');
}
