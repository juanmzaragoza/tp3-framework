from pox.core import core
import pox.openflow.libopenflow_01 as of
import time

log = core.getLogger()


#Si se trata de enviar MAX_PACKETS_PER_TIME en menos de TIME_PACKETS
#Al mismo destino
#Se bloquea por BLOCK_TIME los paquetes que iban hacia dicho destino
MAX_PACKETS_PER_TIME = 100
TIME_PACKETS = 10
BLOCK_TIME = 10

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

  def send_data(self, eth_dst, exit_port, data):
    if time.time() > self.last_time + TIME_PACKETS:
      self.reset_count()
      self.last_time = time.time()

    if eth_dst not in self.packet_count:
      self.packet_count[eth_dst] = 0

    if self.packet_count[eth_dst] >= MAX_PACKETS_PER_TIME:
      msg = of.ofp_flow_mod()
      #msg.match = of.ofp_match.from_packet(packet)
      msg.match.dl_dst = eth_dst
      msg.idle_timeout = BLOCK_TIME
      msg.hard_timeout = BLOCK_TIME
    
      self.connection.send(msg)
    else:
      msg = of.ofp_packet_out()
      msg.data = data
      msg.actions.append(of.ofp_action_output(port = exit_port))

      self.connection.send(msg)

      self.packet_count[eth_dst] += 1

  def add_route_with_data(self, in_port, exit_port, eth_src, eth_dst, eth_type, ip_src, ip_dst, ip_type, data):
    msg = of.ofp_flow_mod()
    msg.data = data
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

    log.info("Sending to switch (NODATA): %s from %s to %s port in: %s out: %s", self.dpid, eth_src, eth_dst, in_port, exit_port)

  def _handle_PacketIn(self, event):
    """
    Esta funcion es llamada cada vez que el switch recibe un paquete
    y no encuentra en su tabla una regla para rutearlo
    """
    packet = event.parsed

    # Un paquete arribo por el puerto event.port veamos si es un host
    if (event.port not in self.ports):
      #Lo linkeamos a ese puerto - Puerto->MAC host
      self.hosts[event.port] = packet.src
    
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
    self.cost += 1
