import React from 'react';
import {createRoot} from 'react-dom/client';

const basePath = new URL(import.meta.env.BASE_URL, window.location.origin).pathname.replace(/\/$/, '');
const pathname = window.location.pathname.replace(/\/$/, '');

if (pathname === `${basePath}/overview`) {
  document.documentElement.dataset.salusOverview = '';
  document.documentElement.lang = 'en';
  document.title = 'Project Salus · Crew health, mission context, informed decisions';
  document.querySelector('meta[name="theme-color"]').content = '#041632';
  const description = document.createElement('meta');
  description.name = 'description';
  description.content = 'Explore Project Salus: crew health, mission operations, emerging risk signals, and evidence-linked recommendations in one workspace. See the product with demo data.';
  document.head.append(description);
  import('./Overview.jsx').then(({default: Overview}) => {
    createRoot(document.getElementById('root')).render(<Overview/>);
  });
} else {
  import('./main.jsx');
}
