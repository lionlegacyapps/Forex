import { Router, Response } from 'express';
import { PrismaClient } from '@prisma/client';
import axios from 'axios';
import { authenticate, AuthRequest, resolveTenant } from '../middleware/auth';

const router = Router();
const prisma = new PrismaClient();

router.use(authenticate);

async function callDeepSeek(messages: { role: string; content: string }[], systemPrompt: string) {
  const apiKey = process.env.DEEPSEEK_API_KEY;

  // Return null (mock mode) if no real API key configured
  if (!apiKey || apiKey.startsWith('your-')) {
    return null;
  }

  const response = await axios.post(
    'https://api.deepseek.com/chat/completions',
    {
      model: 'deepseek-chat',
      messages: [{ role: 'system', content: systemPrompt }, ...messages],
      temperature: 0.7,
      max_tokens: 2000,
    },
    {
      headers: {
        Authorization: `Bearer ${apiKey}`,
        'Content-Type': 'application/json',
      },
    }
  );

  return response.data.choices[0].message.content;
}

// AI Chat assistant
router.post('/chat', async (req: AuthRequest, res: Response) => {
  try {
    const tenantId = resolveTenant(req);
    const { messages, context } = req.body;

    const systemPrompt = `You are TruckDispatch AI, an expert freight dispatcher assistant. You help dispatchers with:
- Load matching: suggesting the best driver for a load based on location, HOS hours, equipment type
- Rate negotiation: analyzing market rates and suggesting competitive pricing
- Route optimization: considering fuel costs, tolls, weather, and HOS regulations
- Problem solving: handling delays, breakdowns, and weather issues
- Compliance: DOT regulations, HOS rules, FMCSA requirements

Current context: ${JSON.stringify(context || {})}
You have access to real-time data about drivers and loads. Be concise, practical, and data-driven.
Always format rates in USD. Use trucking industry terminology.`;

    const aiResponse = await callDeepSeek(messages, systemPrompt);

    if (!aiResponse) {
      // Mock intelligent responses when no API key
      const lastMessage = messages[messages.length - 1]?.content?.toLowerCase() || '';
      let mockResponse = '';

      if (lastMessage.includes('load') && (lastMessage.includes('match') || lastMessage.includes('assign') || lastMessage.includes('best driver'))) {
        mockResponse = `**Load Matching Analysis**\n\nBased on current driver positions and HOS availability, here are my top recommendations:\n\n1. **Carlos Martinez (T-101)** — Score: 9.4/10\n   - Currently in Dallas, TX (near pickup)\n   - 9.5 hours drive time remaining\n   - Equipment: Dry Van ✓\n   - 342 loads completed, 4.9 rating\n\n2. **Mike Thompson (T-104)** — Score: 8.1/10\n   - Houston, TX (2.5 hrs from pickup)\n   - 11.0 hours drive time remaining\n   - Equipment: Reefer ✓\n\n**Recommendation:** Dispatch Carlos Martinez — closest to origin, excellent HOS remaining, top-rated driver.`;
      } else if (lastMessage.includes('rate') || lastMessage.includes('price') || lastMessage.includes('negotiate')) {
        mockResponse = `**Rate Analysis**\n\nCurrent market conditions for this lane:\n\n📊 **Market Data**\n- DAT Average: $2.85/mile\n- Current Market: $2.92/mile (+2.5% vs 30-day avg)\n- Fuel Surcharge Index: $0.48/mile\n\n💡 **Recommendation**\n- **Target Rate:** $3.10/mile ($2.62 base + $0.48 FSC)\n- **Floor Rate:** $2.75/mile (break-even with driver pay)\n- **Ceiling Rate:** $3.40/mile (high demand scenario)\n\n**Negotiation Tip:** The broker is at $2.90/mile. Counter at $3.15 — market supports it and this lane has historically paid above average.`;
      } else if (lastMessage.includes('weather') || lastMessage.includes('storm') || lastMessage.includes('route')) {
        mockResponse = `**Route & Weather Advisory**\n\n⚠️ **Active Alerts on I-40 Corridor:**\n- Winter Storm Warning: NM/AZ border (thru tomorrow 6pm)\n- Reduced visibility possible, roads may be icy\n- Chain law in effect on Flagstaff grades\n\n🗺️ **Alternate Route Suggestion:**\n- Primary: I-40 West → Add 3-4 hrs delay risk\n- **Alternate: I-10 South via El Paso** → +85 miles but weather-clear\n- Additional fuel cost: ~$42\n- Time savings vs waiting: 2.5 hours net\n\n**Recommendation:** Reroute via I-10 if load is time-sensitive. Notify driver and broker of alternate routing.`;
      } else if (lastMessage.includes('hos') || lastMessage.includes('hours') || lastMessage.includes('compliance')) {
        mockResponse = `**HOS Compliance Check**\n\n📋 **Driver Hours Summary:**\n\n| Driver | Drive Remaining | Shift Remaining | Status |\n|--------|----------------|-----------------|--------|\n| D. Johnson | 4.5 hrs ⚠️ | 6.0 hrs | DRIVING |\n| J. Davis | 8.0 hrs | 11.0 hrs | ON_DUTY |\n| C. Martinez | 9.5 hrs ✓ | 12.0 hrs | AVAILABLE |\n\n⚠️ **Action Required:** David Johnson is approaching HOS limit on load AL-2024-001. Estimated delivery is 5.5 hours out — tight but within legal limits.\n\n**Recommendation:** Monitor Johnson's progress. If behind schedule by 30+ minutes, pre-arrange a team driver swap or authorize a 34-hour restart.`;
      } else {
        mockResponse = `I'm your AI dispatch assistant. I can help you with:\n\n🚛 **Load Matching** — "Who's the best driver for load #AL-2024-002?"\n💰 **Rate Negotiation** — "What's a fair rate for Dallas to LA?"\n🗺️ **Route Planning** — "Any weather issues on the I-40 today?"\n⏱️ **HOS Monitoring** — "Which drivers are near their hours limit?"\n📞 **Broker Communication** — "Draft me a check-call message"\n\nWhat do you need help with today?`;
      }

      return res.json({ success: true, data: { message: mockResponse, source: 'mock' } });
    }

    return res.json({ success: true, data: { message: aiResponse, source: 'deepseek' } });
  } catch (e) {
    console.error(e);
    return res.status(500).json({ success: false, error: 'AI service error' });
  }
});

// Load matching AI
router.post('/match-load', async (req: AuthRequest, res: Response) => {
  try {
    const tenantId = resolveTenant(req);
    const { loadId } = req.body;

    const load = await prisma.load.findUnique({
      where: { id: loadId },
      include: { stops: { orderBy: { sequence: 'asc' } } },
    });

    if (!load) return res.status(404).json({ success: false, error: 'Load not found' });

    const pickupStop = load.stops[0];
    const driverWhere: Record<string, unknown> = { status: 'AVAILABLE', isActive: true, hosDriveRemaining: { gte: 4 } };
    if (tenantId) driverWhere.tenantId = tenantId;

    const drivers = await prisma.driver.findMany({ where: driverWhere });

    // Score drivers
    const scored = drivers.map((d) => {
      let score = 70;

      // Equipment match
      const dEquip = d.equipmentTypes.split(',');
      if (dEquip.includes(load.equipmentType)) score += 20;

      // HOS score (more hours = higher score)
      score += Math.min(d.hosDriveRemaining * 0.5, 5);

      // Rating bonus
      score += (d.rating - 4) * 5;

      // Distance to pickup (mock calculation)
      let distanceToPickup = 0;
      if (d.currentLat && d.currentLng && pickupStop?.lat && pickupStop?.lng) {
        const R = 3959;
        const dLat = ((pickupStop.lat - d.currentLat) * Math.PI) / 180;
        const dLon = ((pickupStop.lng - d.currentLng) * Math.PI) / 180;
        const a = Math.sin(dLat / 2) ** 2 + Math.cos((d.currentLat * Math.PI) / 180) * Math.cos((pickupStop.lat * Math.PI) / 180) * Math.sin(dLon / 2) ** 2;
        distanceToPickup = R * 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1 - a));
      } else {
        distanceToPickup = Math.random() * 500 + 50;
      }

      // Distance penalty
      if (distanceToPickup < 100) score += 10;
      else if (distanceToPickup > 500) score -= 10;

      const reasons: string[] = [];
      if (dEquip.includes(load.equipmentType)) reasons.push(`Has required ${load.equipmentType} equipment`);
      if (d.hosDriveRemaining >= 10) reasons.push(`${d.hosDriveRemaining}h drive time available`);
      if (d.rating >= 4.8) reasons.push(`Top-rated driver (${d.rating}★)`);
      if (distanceToPickup < 150) reasons.push(`Only ${Math.round(distanceToPickup)} miles from pickup`);
      if (d.totalLoads > 300) reasons.push(`Experienced (${d.totalLoads} loads completed)`);

      return {
        driverId: d.id,
        driver: { ...d, equipmentType: d.equipmentTypes.split(',') },
        score: Math.min(Math.round(score), 100),
        reasons,
        estimatedPickupTime: new Date(Date.now() + (distanceToPickup / 55) * 3600000).toISOString(),
        distanceToPickup: Math.round(distanceToPickup),
      };
    });

    scored.sort((a, b) => b.score - a.score);

    return res.json({ success: true, data: scored.slice(0, 5) });
  } catch (e) {
    console.error(e);
    return res.status(500).json({ success: false, error: 'Server error' });
  }
});

// Rate suggestion AI
router.post('/suggest-rate', async (req: AuthRequest, res: Response) => {
  try {
    const { originCity, originState, destCity, destState, equipmentType, miles, weight } = req.body;

    // Market rate data (mock — real implementation queries DAT or Truckstop API)
    const marketRates: Record<string, number> = {
      DRY_VAN: 2.85,
      REEFER: 3.20,
      FLATBED: 3.10,
      STEP_DECK: 3.25,
      TANKER: 3.50,
      HOTSHOT: 4.00,
      POWER_ONLY: 2.20,
    };

    const baseRate = marketRates[equipmentType as string] || 2.85;
    const fuelSurcharge = 0.48;
    const totalPerMile = baseRate + fuelSurcharge;
    const totalRate = Math.round(totalPerMile * (miles || 500));

    const systemMsg = `You are a freight rate expert. Analyze this lane and provide a rate recommendation in JSON format.`;
    const userMsg = `Lane: ${originCity}, ${originState} to ${destCity}, ${destState}. Equipment: ${equipmentType}. Miles: ${miles}. Weight: ${weight} lbs. Market rate: $${baseRate}/mile.`;

    const aiResponse = await callDeepSeek([{ role: 'user', content: userMsg }], systemMsg);

    return res.json({
      success: true,
      data: {
        suggestedRate: totalRate,
        minRate: Math.round(totalRate * 0.9),
        maxRate: Math.round(totalRate * 1.15),
        marketRate: Math.round(baseRate * (miles || 500)),
        ratePerMile: Math.round(totalPerMile * 100) / 100,
        confidence: 0.82,
        factors: [
          `Market average for ${equipmentType}: $${baseRate}/mile`,
          `Fuel surcharge index: $${fuelSurcharge}/mile`,
          `Lane demand: Moderate (${Math.random() > 0.5 ? 'above' : 'below'} 30-day avg)`,
          `${originState} to ${destState} corridor: Historically $${(baseRate * 0.95).toFixed(2)}-$${(baseRate * 1.1).toFixed(2)}/mile`,
        ],
        aiInsight: aiResponse,
      },
    });
  } catch {
    return res.status(500).json({ success: false, error: 'Server error' });
  }
});

export { router as aiRouter };
