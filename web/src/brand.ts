// Single source of truth for the product name and links.
export const brand = {
  name: 'HEPLab',
  tagline: 'Reproducible LHC analysis and simulation on CERN Open Data.',
  cli: 'heplab',
  repository: 'https://github.com/adian007/QuantumArtGenerator-Cybersecurity',
} as const

export const repoFile = (path: string) => `${brand.repository}/blob/main/${path}`
