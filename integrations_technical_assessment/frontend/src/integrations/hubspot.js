import { useState, useEffect } from 'react';
import {
    Box,
    Button,
    CircularProgress
} from '@mui/material';
import axios from 'axios';

export const HubSpotIntegration = ({ user, org, integrationParams, setIntegrationParams }) => {
    const [isConnected, setIsConnected] = useState(false);
    const [isConnecting, setIsConnecting] = useState(false);

    const handleConnectClick = async () => {
        try {
            setIsConnecting(true);
            const formData = new FormData();
            formData.append('user_id', user);
            formData.append('org_id', org);

            const response = await axios.post(`http://localhost:8000/integrations/hubspot/authorize`, formData);
            const authURL = response?.data?.authorization_url;

            if (!authURL) throw new Error("Authorization URL not received.");

            const newWindow = window.open(authURL, 'HubSpot Authorization', 'width=600,height=600');

            const pollTimer = window.setInterval(() => {
                if (newWindow?.closed !== false) {
                    window.clearInterval(pollTimer);
                    handleWindowClosed();
                }
            }, 300);
        } catch (e) {
            console.error("HubSpot auth error:", e);
            setIsConnecting(false);
            alert(e?.response?.data?.detail || e.message);
        }
    };

    const handleWindowClosed = async () => {
        try {
            const formData = new FormData();
            formData.append('user_id', user);
            formData.append('org_id', org);

            const response = await axios.post(`http://localhost:8000/integrations/hubspot/credentials`, formData);
            const credentials = response.data;

            if (credentials) {
                setIntegrationParams(prev => ({
                    ...prev,
                    credentials: credentials,
                    type: 'HubSpot'
                }));
                setIsConnected(true);
            }
        } catch (e) {
            alert(e?.response?.data?.detail || "Failed to fetch credentials.");
        } finally {
            setIsConnecting(false);
        }
    };

    useEffect(() => {
        setIsConnected(!!integrationParams?.credentials);
    }, [integrationParams]);

    return (
        <Box sx={{ mt: 2 }}>
            <div>Parameters</div>
            <Box display="flex" alignItems="center" justifyContent="center" sx={{ mt: 2 }}>
                <Button
                    variant="contained"
                    onClick={isConnected ? undefined : handleConnectClick}
                    color={isConnected ? 'success' : 'primary'}
                    disabled={isConnecting}
                    sx={{
                        pointerEvents: isConnected ? 'none' : 'auto',
                        cursor: isConnected ? 'default' : 'pointer',
                    }}
                >
                    {isConnected
                        ? 'HubSpot Connected'
                        : isConnecting
                            ? <CircularProgress size={20} />
                            : 'Connect to HubSpot'}
                </Button>
            </Box>
        </Box>
    );
};
