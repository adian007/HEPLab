import { defineConfig } from 'astro/config'
import starlight from '@astrojs/starlight'

const repository = 'https://github.com/adian007/HEPLab.git'

export default defineConfig({
  site: 'https://heplab.org',
  output: 'static',
  integrations: [
    starlight({
      title: 'HEPLab',
      description: 'Local LHC simulation and analysis on CERN Open Data, with evidence and limits kept in view.',
      disable404Route: true,
      logo: {
        src: './public/heplab-detector.png',
        alt: 'HEPLab',
      },
      favicon: '/heplab-detector.svg',
      social: [
        { icon: 'github', label: 'HEPLab on GitHub', href: repository },
      ],
      editLink: {
        baseUrl: `${repository}/edit/main/web/`,
      },
      customCss: ['./src/styles/site.css'],
      lastUpdated: true,
      sidebar: [
        {
          label: 'Start here',
          items: ['index', 'getting-started'],
        },
        {
          label: 'Project',
          items: ['project/capabilities', 'project/roadmap', 'project/limitations'],
        },
        {
          label: 'Use HEPLab',
          items: ['simulation/workbench', 'simulation/models', 'data/open-data', 'analysis/workflow', 'education', 'results', 'gallery'],
        },
        {
          label: 'Evidence',
          items: ['validation/evidence', 'validation/reading-results'],
        },
        {
          label: 'Reference',
          items: ['architecture', 'reference/api', 'reference/python-api-v1', 'contributing', 'faq'],
        },
      ],
    }),
  ],
})
