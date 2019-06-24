from pox.core import core
import pox.openflow.libopenflow_01 as of
import time
from pox.openflow.of_json import *

log = core.getLogger()


#Si se trata de enviar MAX_PACKETS_PER_TIME en menos de TIME_PACKETS
#Al mismo destino
#Se bloquea por BLOCK_TIME los paquetes que iban hacia dicho destino
MAX_PACKETS_PER_TIME = 50
TIME_PACKETS = 10
BLOCK_TIME = 5

class SwitchController:
  def __init__(self, dpid, connection, base_controller):
    self.dpid = dpid
    self.connection = connection
    # El SwitchController se agrega como handler de los eventos del switch
    self.connection.addListeners(self)  
    self.base_controller = base_controller
    self.ports = {}
    self.hosts = {}
    self.cost = 1

    self.last_time = time.time()
    self.packet_count = {}

    self.routes = []
    self.blocked = {}

  def cost_traffic(self):
    return self.cost
  
  def add_link_port(self, switch_id, port):
    self.ports[port] = switch_id

  def ports_adyascents(self):
    return self.ports.items()
  
  def hosts_adyascents(self):
    return self.hosts.items()

  def reset_count(self):
    for dest in self.packet_count.keys():
      self.packet_count[dest] = 0

  def block_flow(self, eth_dst):
      log.info("Switch %s - Blocked %s", self.dpid, eth_dst)

      msg = of.ofp_flow_mod()
      msg.match.dl_dst = eth_dst
      msg.idle_timeout = BLOCK_TIME
      msg.hard_timeout = BLOCK_TIME
      msg.flags = of.OFPFF_SEND_FLOW_REM
      msg.command = of.OFPFC_DELETE

      self.blocked[eth_dst] = True

      self.connection.send(msg)    

      msg = of.ofp_flow_mod()
      msg.match.dl_dst = eth_dst
      msg.idle_timeout = BLOCK_TIME
      msg.hard_timeout = BLOCK_TIME
      msg.flags = of.OFPFF_SEND_FLOW_REM
      msg.command = of.OFPFC_ADD

      self.connection.send(msg)    

  def add_route_with_data(self, in_port, exit_port, eth_src, eth_dst, eth_type, ip_src, ip_dst, ip_type, data):
    msg = of.ofp_flow_mod()
    msg.data = data
    msg.command = of.OFPFC_ADD
    msg.match.dl_dst = eth_dst
    msg.match.dl_src = eth_src
    msg.match.in_port = in_port
    msg.match.dl_type = eth_type
    msg.match.nw_src = ip_src
    msg.match.nw_dst = ip_dst
    msg.match.nw_proto = ip_type

    #Quizas lo de abajo implique todo lo de arriba
    #msg.match = of.ofp_match.from_packet(packet)
    msg.actions.append(of.ofp_action_output(port = exit_port))

    log.info("Sending to switch: %s from %s to %s port in: %s out: %s", self.dpid, eth_src, eth_dst, in_port, exit_port)

    self.connection.send(msg)

  def add_route(self, in_port, exit_port, eth_src, eth_dst, eth_type, ip_src, ip_dst, ip_type):
    self.routes.append([in_port, eth_src, eth_dst, eth_type, ip_src, ip_dst, ip_type, exit_port])
    # Aumentamos el costo de pasar por este switch en 1 para controlar
    # el trafico
    self.cost += 1

    #log.info("Sending to switch (NODATA): %s from %s to %s port in: %s out: %s", self.dpid, eth_src, eth_dst, in_port, exit_port)

  def _handle_PacketIn(self, event):
    """
    Esta funcion es llamada cada vez que el switch recibe un paquete
    y no encuentra en su tabla una regla para rutearlo
    """
    packet = event.parsed

    if packet.dst not in self.blocked:
      self.blocked[packet.dst] = False

    #Drop incoming packets if its blocked
    if self.blocked[packet.dst] == True:
      return

    # Un paquete arribo por el puerto event.port veamos si es un host
    if (event.port not in self.ports):
      #Lo linkeamos a ese puerto - Puerto->MAC host
      self.hosts[event.port] = packet.src
    
    #log.info("Packet arrived switch: %s. From %s to %s", self.dpid, packet.src, packet.dst)

    for in_port, eth_src, eth_dst, eth_type, ip_src, ip_dst, ip_type, exit_port in self.routes:
      if (event.port == in_port and
        eth_src == packet.src and
        eth_dst == packet.dst and
        eth_type == packet.type and
        ip_src == packet.payload.srcip and
        ip_dst == packet.payload.dstip and
        ip_type == packet.payload.protocol):

        self.add_route_with_data(in_port, exit_port, eth_src, eth_dst, eth_type, ip_src, ip_dst, ip_type, event.ofp)
        return

    # Obtenemos y asignamos una ruta hacia el destino
    self.base_controller.assign_route(self.dpid, packet, event.port, event.ofp)

    # Aumentamos el costo de pasar por este switch en 1 para controlar
    # el trafico
    #self.cost += 1

  def _handle_FlowStatsReceived(self, event):
    #Este metodo se llama cada TIMER_SECONDS
    stats = flow_stats_to_list(event.stats)

    web_bytes = 0
    web_flows = 0
    web_packet = {}

    dests = []

    for f in event.stats:
      #log.info("Matches: %s", f.match)
      if f.match.dl_dst and f.match.nw_proto:
        #Only UDP : UDP_PROTOCOL = 17
        if f.match.nw_proto == 17:
          dests.append(f.match.dl_dst)

          if f.match.dl_dst not in self.packet_count:
            self.packet_count[f.match.dl_dst] = 0
          if f.match.dl_dst not in web_packet:
            web_packet[f.match.dl_dst] = 0

          web_bytes += f.byte_count
          
          web_packet[f.match.dl_dst] += f.packet_count

          web_flows += 1
    
    #Si la cantidad de paquetes recibidos en TIMER_SECONDS segundos
    #Supera un umbral de MAX_PACKETS_PER_TIME cada TIMER_SECONDS segundos
    #Bloqueamos los paquetes hacia dicho destino por un tiempo definido
    for dest in dests:
      #log.info("Packets sent to %s - %s/%s", dest, self.packet_count[dest], web_packet[dest])
      if web_packet[dest] - self.packet_count[dest] >= MAX_PACKETS_PER_TIME:
        #Reseteamos los paquetes porque vamos a eliminar el flujo
        web_packet[dest] = 0
        self.block_flow(dest)

      self.packet_count[dest] = web_packet[dest]
    

    log.info("Web traffic from %s: %s bytes over %s flows", self.dpid, web_bytes, web_flows)
    #log.info("FlowStatsReceived from %s: %s", dpidToStr(event.connection.dpid), stats)

  def _handle_PortStatsReceived(self, event):
    pass

  def _handle_FlowRemoved(self, event):
    if event.deleted == False:
      self.blocked[event.ofp.match.dl_dst] = False
