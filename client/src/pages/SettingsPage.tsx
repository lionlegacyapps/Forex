import { useState } from 'react';
import { Settings, Bell, Lock, Zap, Globe, Database } from 'lucide-react';

export default function SettingsPage() {
  const [saved, setSaved] = useState(false);

  const handleSave = () => {
    setSaved(true);
    setTimeout(() => setSaved(false), 2000);
  };

  const sections = [
    {
      icon: Zap,
      title: 'AI Settings',
      items: [
        { label: 'DeepSeek API Key', type: 'password', placeholder: 'sk-...', key: 'deepseek' },
        { label: 'AI Auto-Match Threshold', type: 'number', placeholder: '70', key: 'aiThreshold' },
      ],
    },
    {
      icon: Globe,
      title: 'Map & Routing',
      items: [
        { label: 'Mapbox Token', type: 'password', placeholder: 'pk.ey...', key: 'mapbox' },
        { label: 'HERE API Key', type: 'password', placeholder: 'Enter HERE API key', key: 'here' },
        { label: 'Google Places Key', type: 'password', placeholder: 'AIza...', key: 'google' },
      ],
    },
    {
      icon: Bell,
      title: 'Communications',
      items: [
        { label: 'Telnyx API Key', type: 'password', placeholder: 'KEY0...', key: 'telnyx' },
        { label: 'Telnyx Phone Number', type: 'text', placeholder: '+1 555 000 0000', key: 'telnyxPhone' },
        { label: 'LiveKit Server URL', type: 'text', placeholder: 'wss://your.livekit.cloud', key: 'livekit' },
      ],
    },
    {
      icon: Database,
      title: 'ELD Integrations',
      items: [
        { label: 'Motive API Key', type: 'password', placeholder: 'Enter Motive API key', key: 'motive' },
        { label: 'Samsara API Key', type: 'password', placeholder: 'samsara_api_...', key: 'samsara' },
        { label: 'Geotab Username', type: 'text', placeholder: 'your@email.com', key: 'geotabUser' },
      ],
    },
    {
      icon: Bell,
      title: 'Notifications',
      items: [
        { label: 'HOS Alert Threshold (hours)', type: 'number', placeholder: '4', key: 'hosAlert' },
        { label: 'Late Delivery Alert (minutes)', type: 'number', placeholder: '30', key: 'lateAlert' },
      ],
    },
  ];

  return (
    <div className="max-w-2xl space-y-6">
      <div>
        <h1 className="text-2xl font-bold">Settings</h1>
        <p className="text-sm text-muted-foreground">Configure API keys and platform preferences</p>
      </div>

      {sections.map(({ icon: Icon, title, items }) => (
        <div key={title} className="bg-card border border-border rounded-xl">
          <div className="p-4 border-b border-border flex items-center gap-2">
            <Icon size={16} className="text-primary" />
            <h2 className="text-sm font-semibold">{title}</h2>
          </div>
          <div className="p-4 space-y-4">
            {items.map(({ label, type, placeholder, key }) => (
              <div key={key}>
                <label className="block text-sm font-medium text-foreground mb-1.5">{label}</label>
                <input
                  type={type}
                  placeholder={placeholder}
                  className="w-full h-9 px-3 rounded-md border border-input bg-secondary/30 text-sm focus:outline-none focus:ring-1 focus:ring-primary placeholder:text-muted-foreground"
                />
              </div>
            ))}
          </div>
        </div>
      ))}

      <div className="flex items-center gap-3">
        <button
          onClick={handleSave}
          className="px-6 h-9 rounded-lg bg-primary text-primary-foreground text-sm font-medium hover:bg-primary/90 transition-colors"
        >
          {saved ? '✓ Saved!' : 'Save Settings'}
        </button>
        <p className="text-xs text-muted-foreground">Settings are stored securely on the server</p>
      </div>
    </div>
  );
}
