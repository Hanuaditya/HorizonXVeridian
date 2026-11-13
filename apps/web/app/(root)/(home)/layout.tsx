import { Metadata } from 'next';
import React, { ReactNode } from 'react';
import HomeLayoutClient from './HomeLayoutClient';

export const metadata: Metadata = {
  title: 'Horizon Veridian',
  description: 'Sovereign Indic Voice & Agentic WorkOS Platform',
  icons: {
    icon: '/icons/logo.svg',
  },
};

const HomeLayout = ({ children }: { children: ReactNode }) => {
  return <HomeLayoutClient>{children}</HomeLayoutClient>;
};

export default HomeLayout;
