import { Component, createElement, type ComponentType, type ReactNode } from 'react';
import { createRoot } from 'react-dom/client';
import type { ApplicationModuleProps, ModuleRuntimeContext } from './types';

class ModuleErrorBoundary extends Component<
	{ children: ReactNode; onError: (error: Error) => void },
	{ failed: boolean }
> {
	state = { failed: false };

	static getDerivedStateFromError() {
		return { failed: true };
	}

	componentDidCatch(error: Error) {
		this.props.onError(error);
	}

	render() {
		return this.state.failed ? null : this.props.children;
	}
}

export const mountReactModule = (
	container: HTMLElement,
	moduleId: string,
	Module: ComponentType<ApplicationModuleProps>,
	context: ModuleRuntimeContext,
	onError: (error: Error) => void
) => {
	const root = createRoot(container, { identifierPrefix: `module-${moduleId}-` });
	root.render(
		createElement(
			ModuleErrorBoundary,
			{ onError, children: createElement(Module, { context }) }
		)
	);
	return { unmount: () => root.unmount() };
};
