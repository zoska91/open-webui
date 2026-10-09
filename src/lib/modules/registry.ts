import type { ApplicationModule } from './types';

/** Importing the menu does not load React or any module's implementation. */
export const applicationModules: readonly ApplicationModule[] = [
	{
		id: 'dashboard',
		title: 'Pulpit',
		icon: 'dashboard',
		path: '/modules/dashboard',
		load: () => import('./dashboard/Dashboard')
	}
];

export const getApplicationModule = (id: string): ApplicationModule | undefined =>
	applicationModules.find((module) => module.id === id);
