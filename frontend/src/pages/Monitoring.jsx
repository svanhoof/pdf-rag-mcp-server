import React, { useCallback, useMemo } from 'react';
import {
  Badge,
  Box,
  Button,
  Divider,
  Flex,
  Heading,
  Stack,
  Text,
} from '@chakra-ui/react';
import { useWebSocket } from '../context/WebSocketContext';

const Monitoring = () => {
  const {
    isConnected,
    connectionSnapshot,
    refreshConnectionSnapshot,
  } = useWebSocket();

  const snapshotGeneratedAt = connectionSnapshot?.generatedAt ?? null;

  const formatStatusLabel = useCallback((status) => {
    if (typeof status !== 'string' || status.length === 0) {
      return 'Unknown';
    }
    return status.charAt(0).toUpperCase() + status.slice(1);
  }, []);

  const statusColorScheme = useCallback((status) => {
    if (!status) {
      return 'gray';
    }
    const normalized = status.toLowerCase();
    if (normalized === 'connected') {
      return 'green';
    }
    if (normalized === 'disconnected') {
      return 'red';
    }
    if (normalized === 'error') {
      return 'orange';
    }
    return 'gray';
  }, []);

  const formatTimestamp = useCallback((value) => {
    if (!value) {
      return '—';
    }
    const timestamp = new Date(value);
    if (Number.isNaN(timestamp.getTime())) {
      return '—';
    }
    return timestamp.toLocaleString();
  }, []);

  const formatClientAddress = useCallback((clientHost, clientPort) => {
    if (!clientHost && !clientPort) {
      return 'Unknown client';
    }
    return clientPort ? `${clientHost ?? 'Unknown'}:${clientPort}` : (clientHost ?? 'Unknown client');
  }, []);

  const sortedWebsocketClients = useMemo(() => {
    const websocketClients = connectionSnapshot?.websocketClients ?? [];
    const entries = Array.isArray(websocketClients) ? [...websocketClients] : [];
    entries.sort((a, b) => {
      const aConnected = (a?.status ?? '').toLowerCase() === 'connected';
      const bConnected = (b?.status ?? '').toLowerCase() === 'connected';
      if (aConnected !== bConnected) {
        return aConnected ? -1 : 1;
      }
      const aTime = a?.connected_at ? new Date(a.connected_at).getTime() : 0;
      const bTime = b?.connected_at ? new Date(b.connected_at).getTime() : 0;
      return bTime - aTime;
    });
    return entries;
  }, [connectionSnapshot?.websocketClients]);

  const sortedMcpSessions = useMemo(() => {
    const mcpSessions = connectionSnapshot?.mcpSessions ?? [];
    const entries = Array.isArray(mcpSessions) ? [...mcpSessions] : [];
    entries.sort((a, b) => {
      const aConnected = (a?.status ?? '').toLowerCase() === 'connected';
      const bConnected = (b?.status ?? '').toLowerCase() === 'connected';
      if (aConnected !== bConnected) {
        return aConnected ? -1 : 1;
      }
      const aTime = a?.connected_at ? new Date(a.connected_at).getTime() : 0;
      const bTime = b?.connected_at ? new Date(b.connected_at).getTime() : 0;
      return bTime - aTime;
    });
    return entries;
  }, [connectionSnapshot?.mcpSessions]);

  return (
    <Stack spacing={{ base: 6, lg: 8 }}>
      <Stack spacing={2}>
        <Heading as="h1" size={{ base: 'lg', md: 'xl' }}>Monitoring</Heading>
        <Text color="gray.600" fontSize={{ base: 'sm', md: 'md' }}>
          Monitor live dashboard sockets and MCP clients in one view.
        </Text>
      </Stack>

      <Box bg="white" p={{ base: 5, md: 6 }} shadow="md" borderRadius="lg">
        <Flex justify="space-between" align={{ base: 'flex-start', md: 'center' }} gap={3} mb={3} direction={{ base: 'column', md: 'row' }}>
          <Box>
            <Heading as="h2" size="md" mb={1}>
              Client Connections
            </Heading>
            <Text fontSize="sm" color="gray.600">
              Real-time connection status for dashboard and MCP clients.
            </Text>
          </Box>
          <Button size="sm" variant="outline" onClick={refreshConnectionSnapshot}>
            Refresh
          </Button>
        </Flex>

        <Stack spacing={3}>
          <Flex align="center" gap={3}>
            <Text fontWeight="semibold" fontSize="sm">
              Dashboard socket
            </Text>
            <Badge colorScheme={isConnected ? 'green' : 'red'}>
              {isConnected ? 'Connected' : 'Disconnected'}
            </Badge>
          </Flex>

          {snapshotGeneratedAt && (
            <Text fontSize="xs" color="gray.500">
              Last update: {formatTimestamp(snapshotGeneratedAt)}
            </Text>
          )}

          <Divider />

          <Box>
            <Flex justify="space-between" align="center">
              <Text fontWeight="semibold" fontSize="sm">
                Web dashboard clients
              </Text>
              <Badge colorScheme={sortedWebsocketClients.length ? 'blue' : 'gray'}>
                {sortedWebsocketClients.length}
              </Badge>
            </Flex>
            <Box mt={2} maxH="300px" overflowY="auto">
              {sortedWebsocketClients.length ? (
                <Stack spacing={2}>
                  {sortedWebsocketClients.map((client) => (
                    <Box key={client.connection_id ?? `${client.client_host}-${client.client_port}`} borderWidth="1px" borderColor="gray.100" borderRadius="md" p={3}>
                      <Flex justify="space-between" align="baseline" mb={1}>
                        <Text fontWeight="medium" fontSize="sm">
                          {formatClientAddress(client.client_host, client.client_port)}
                        </Text>
                        <Badge colorScheme={statusColorScheme(client.status)}>
                          {formatStatusLabel(client.status)}
                        </Badge>
                      </Flex>
                      <Text fontSize="xs" color="gray.600">
                        Path: {client.path || '—'}
                      </Text>
                      <Text fontSize="xs" color="gray.600">
                        Connected: {formatTimestamp(client.connected_at)}
                      </Text>
                    </Box>
                  ))}
                </Stack>
              ) : (
                <Text fontSize="sm" color="gray.500">
                  No active dashboard clients
                </Text>
              )}
            </Box>
          </Box>

          <Divider />

          <Box>
            <Flex justify="space-between" align="center">
              <Text fontWeight="semibold" fontSize="sm">
                MCP clients
              </Text>
              <Badge colorScheme={sortedMcpSessions.length ? 'purple' : 'gray'}>
                {sortedMcpSessions.filter((session) => (session?.status ?? '').toLowerCase() === 'connected').length}
                {sortedMcpSessions.length > 0 ? ` / ${sortedMcpSessions.length}` : ''}
              </Badge>
            </Flex>
            <Box mt={2} maxH="300px" overflowY="auto">
              {sortedMcpSessions.length ? (
                <Stack spacing={2}>
                  {sortedMcpSessions.map((session) => (
                    <Box key={session.session_id} borderWidth="1px" borderColor="gray.100" borderRadius="md" p={3}>
                      <Flex justify="space-between" align="baseline" mb={1}>
                        <Text fontWeight="medium" fontSize="sm">
                          {formatClientAddress(session.client_host, session.client_port)}
                        </Text>
                        <Badge colorScheme={statusColorScheme(session.status)}>
                          {formatStatusLabel(session.status)}
                        </Badge>
                      </Flex>
                      <Text fontSize="xs" color="gray.600">
                        Session: {session.session_uuid?.slice(0, 8) ?? session.session_id?.slice(0, 8) ?? '—'}
                      </Text>
                      <Text fontSize="xs" color="gray.600">
                        Connected: {formatTimestamp(session.connected_at)}
                      </Text>
                      <Text fontSize="xs" color="gray.600">
                        Last activity: {formatTimestamp(session.last_message_at || session.disconnected_at || session.connected_at)}
                      </Text>
                      <Text fontSize="xs" color="gray.600">
                        Messages received: {session.messages_received ?? 0}
                      </Text>
                    </Box>
                  ))}
                </Stack>
              ) : (
                <Text fontSize="sm" color="gray.500">
                  No MCP clients connected yet
                </Text>
              )}
            </Box>
          </Box>

          <Divider />

          <Text fontSize="xs" color="gray.600">
            Configure in your AI/LLM chat client: Settings → MCP Servers → Add URL: http://MCP-SERVER-IP:DOCKER_PORT/mcp
          </Text>
        </Stack>
      </Box>
    </Stack>
  );
};

export default Monitoring;
