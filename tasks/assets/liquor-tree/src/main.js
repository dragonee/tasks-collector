import TreeRoot from './components/TreeRoot'

const install = (app) => {
  app.component(TreeRoot.name, TreeRoot)
}

TreeRoot.install = install

export default TreeRoot
