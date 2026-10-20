import '@testing-library/jest-dom/vitest'
import { cleanup, configure } from '@testing-library/react'
import { afterEach, vi } from 'vitest'

afterEach(() => { cleanup(); vi.unstubAllGlobals() })

// CI and clean Docker builds can share CPU. Keep actual UI assertions, while
// allowing chained API effects enough time to settle on slower machines.
configure({ asyncUtilTimeout: 5000 })
