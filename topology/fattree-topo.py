"""
Este archivo ejemplifica la creacion de una topologia de mininet
En este caso estamos creando una topologia muy simple con la siguiente forma

   host --- switch --- switch --- host
"""

from mininet.topo import Topo

class FatTreeTopo( Topo ):
  def __init__( self, half_ports = 2, **opts ):
    Topo.__init__(self, **opts)

    levels = half_ports
    if levels >= 2:

      n_switch = 1
      sw_previous_level = []
      for level in range(levels):

        # create switches level
        q_switches = 2 ** level
        sw_current_level = []
        for i in range(q_switches):
            sw_current_level.append(self.addSwitch('sw'+str(n_switch)))
            n_switch = n_switch + 1

        # connect with the previous level
        if len(sw_previous_level) > 0:

          for previous_switch in sw_previous_level:
            for current_switch in sw_current_level:
              self.addLink(previous_switch, current_switch)

          sw_previous_level = sw_current_level

        else: # is first level

          h1 = self.addHost('h1')
          h2 = self.addHost('h2')
          h3 = self.addHost('h3')

          self.addLink(sw_current_level[0], h1)
          self.addLink(sw_current_level[0], h2)
          self.addLink(sw_current_level[0], h3)

          sw_previous_level = sw_current_level

      # create host for leafs
      for i in range(len(sw_current_level)):
        h = self.addHost('h'+str(i+4))
        self.addLink(sw_current_level[i], self.addHost('h'+str(i+4)))

topos = { 'fasttree-topo': FatTreeTopo }
