import type { ComponentType } from 'react';

/** Application data and navigation only; model credentials stay on the server. */
export interface ModuleRuntimeContext {
	locale: string;
	timeZone: string;
	userName: string;
	navigate: (path: string) => void | Promise<void>;
	getJson: <T>(path: string, signal?: AbortSignal) => Promise<T>;
	preferences: {
		get: (key: string) => string | null;
		set: (key: string, value: string) => void;
	};
}

export interface ApplicationModuleProps {
	context: ModuleRuntimeContext;
}

export interface ApplicationModule {
	id: string;
	title: string;
	icon: string;
	path: string;
	load: () => Promise<{ default: ComponentType<ApplicationModuleProps> }>;
}
