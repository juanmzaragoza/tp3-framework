from pox.core import core
import pox.openflow.discovery
import pox.openflow.spanning_tree
import pox.forwarding.l2_learning
from pox.lib.util import dpid_to_str
from extensions.switch import SwitchController
from pox.lib.recoco import Timer

log = core.getLogger()

class Controller:
  def __init__ (self):
    self.connections = set()
    # self.switches = []
    self.switches = {}
    self.paths = {}

    # Esperando que los modulos openflow y openflow_discovery esten listos
    core.call_when_ready(self.startup, ('openflow', 'openflow_discovery'))

  def startup(self):
    """
    Esta funcion se encarga de inicializar el controller
    Agrega el controller como event handler para los eventos de
    openflow y openflow_discovery
    """
    core.openflow.addListeners(self)
    core.openflow_discovery.addListeners(self)
    log.info('Controller initialized')

  def _handle_ConnectionUp(self, event):
    """
    Esta funcion es llamada cada vez que un nuevo switch establece conexion
    Se encarga de crear un nuevo switch controller para manejar los eventos de cada switch
    """
    log.info("Switch %s has come up.", dpid_to_str(event.dpid))
    if (event.connection not in self.connections):
      self.connections.add(event.connection)
      sw = SwitchController(event.dpid, event.connection, self)
      # self.switches.append(sw)
      self.switches[event.dpid] = sw

  def _handle_LinkEvent(self, event):
    """
    Esta funcion es llamada cada vez que openflow_discovery descubre un nuevo enlace
    """
    link = event.link
    #log.info("Link has been discovered from %s,%s to %s,%s", dpid_to_str(link.dpid1), link.port1, dpid_to_str(link.dpid2), link.port2)
    # log.info("Link has been discovered from %d to %d", link.dpid1, link.dpid2)
    #log.info("Ports? %d to %d", link.dpid1, link.dpid2)

    self.switches[link.dpid1].add_link_port(link.dpid2, link.port1)
    self.switches[link.dpid2].add_link_port(link.dpid1, link.port2)

  def assign_route(self, switch_id, packet, port_in, data):
    start = switch_id
    end = packet.dst

    not_visitted = []
    acum_dist = {}
    precesors = {}
    possible_last_switches = []

    for switch in self.switches.keys():
      not_visitted.append(switch)
      acum_dist[switch] = 99999

      for port, mac in self.switches[switch].hosts_adyascents():
        if (end == mac):
          possible_last_switches.append([switch, port])

    #Se desconoce como llegar al host
    if len(possible_last_switches) == 0:
      return

    acum_dist[start] = 0
    last = start

    while (len(not_visitted) > 0):
      not_visitted.remove(last)

      for port, adyascent in self.switches[last].ports_adyascents():
        #Los adyascentes estan a una unidad de distancia
        if (acum_dist[adyascent] > acum_dist[last] + 1):
          acum_dist[adyascent] = acum_dist[last] + 1
          #Append Switch and the port that goes to this switch
          precesors[adyascent] = [last, port]
        
        #Cuando el switch provee un camino al adyascente
        #Con la misma distancia pero
        #Con un costo acumulado menor, se elige el camino
        #con el switch con menor trafico
        elif (acum_dist[adyascent] == acum_dist[last] + 1):
          sw_id, port_ = precesors[adyascent]

          last_cost = self.switches[sw_id].cost_traffic()
          new_cost = self.switches[last].cost_traffic()

          if (last_cost > new_cost):
            #log.info("Overlapping COST")
            precesors[adyascent] = [last, port]          
      
      minor_dist = 99999

      for switch in self.switches.keys():
        if (switch not in not_visitted):
          continue
        
        if (acum_dist[switch] < minor_dist):
          last = switch
          minor_dist = acum_dist[switch]

    # Get shortest path
    path = []

    actual_dist = 99999
    last_switch = 0
    port = 0

    #Por ahora solo tomamos un unico switch adyascente al host destino
    #Esto es valido siempre que se respete fat tree
    #Donde cada datacenter se conecta con un unico switch
    #Por lo que la lista deberia ser de 1 solo elemento
    for switch, p in possible_last_switches:
      if (acum_dist[switch] < actual_dist):
        last_switch = switch
        port = p
        actual_dist = acum_dist[switch]

    #Esta conectado directamente con el switch
    if (last_switch == start):
      path.append([port_in, last_switch, port])
    else:
      while (last_switch in precesors):
        sw, p = precesors[last_switch]

        for p2, sw2 in self.switches[last_switch].ports_adyascents():
          if sw2 == sw:
            path.append([p2, last_switch, port])
            port = p
            break
        last_switch = sw

      path.append([port_in, last_switch, port])

    if (packet.payload.protocol == packet.payload.UDP_PROTOCOL):
        in_port, switch, exit_port = path[-1]
        self.switches[switch].send_data(
          packet.dst,
          exit_port,
          data
        )
        return

    i = 0
    for in_port, switch, exit_port in reversed(path):
      if i == 0:
        self.switches[switch].add_route_with_data(
          in_port,
          exit_port,
          packet.src,
          packet.dst,
          packet.type,
          packet.payload.srcip,
          packet.payload.dstip,
          packet.payload.protocol,
          data
        )
      else:
        self.switches[switch].add_route(
          in_port,
          exit_port,
          packet.src,
          packet.dst,
          packet.type,
          packet.payload.srcip,
          packet.payload.dstip,
          packet.payload.protocol
        )

      i += 1

def launch():
  # Inicializando el modulo openflow_discovery
  pox.openflow.discovery.launch()

  # Registrando el Controller en pox.core para que sea ejecutado
  core.registerNew(Controller)
    
  #core.openflow.addListenerByName("FlowStatsReceived", _handle_FlowStatsReceived) 

  #Timer(5, _timer_func, recurring=True)
  """
  Corriendo Spanning Tree Protocol y el modulo l2_learning.
  No queremos correrlos para la resolucion del TP.
  Aqui lo hacemos a modo de ejemplo
  """
  # pox.openflow.spanning_tree.launch()
  # pox.forwarding.l2_learning.launch()
