import React from "react";
import StatusPanel from "./StatusPanel";
import { WebSocketMessage } from "../../../services/clients";

interface MonitorSectionProps {
  messages: WebSocketMessage[];
  backendStatus: { running: boolean; port: number; pid?: number };
  connections: { api: boolean; websocket: boolean };
}

const MonitorSection: React.FC<MonitorSectionProps> = ({
  messages,
  backendStatus,
  connections,
}) => {
  return (
    <div className="max-w-4xl mx-auto">
      <StatusPanel
        messages={messages}
        backendStatus={backendStatus}
        connections={connections}
      />
    </div>
  );
};

export default MonitorSection;