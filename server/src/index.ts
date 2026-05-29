import dotenv from 'dotenv';
import path from 'path';

// Load from server/.env first (CWD when running from server/), then root
dotenv.config({ path: path.resolve(process.cwd(), '.env') });
dotenv.config({ path: path.resolve(__dirname, '../.env') });
dotenv.config({ path: path.resolve(__dirname, '../../.env') });

import app from './app';

const PORT = process.env.PORT || 3001;

app.listen(PORT, () => {
  console.log(`🚛 TruckDispatch AI server running on http://localhost:${PORT}`);
});

export default app;
