import { Tabs } from "expo-router";
import { Platform } from "react-native";
import { useTranslation } from "react-i18next";
import { useTheme } from "@/src/theme";
import { fonts } from "@/src/lib/typography";
import { Icon, IconName } from "@/src/components/Icon";

export default function GuestLayout() {
  const { colors } = useTheme();
  const { t } = useTranslation();

  const makeIcon = (name: IconName) => {
    const TabBarIcon = ({ color, size }: { color: string; size: number }) => (
      <Icon name={name} size={size ?? 24} color={color} />
    );
    return TabBarIcon;
  };

  return (
    <Tabs
      screenOptions={{
        headerShown: false,
        tabBarActiveTintColor: colors.brandPrimary,
        tabBarInactiveTintColor: colors.muted,
        tabBarStyle: {
          backgroundColor: colors.surfaceSecondary,
          borderTopColor: colors.divider,
          ...(Platform.OS === "web" ? { height: 64 } : {}),
        },
        tabBarItemStyle: { alignSelf: "center" },
        tabBarLabelStyle: { fontFamily: fonts.body, fontSize: 11, fontWeight: "600" },
      }}
    >
      <Tabs.Screen
        name="index"
        options={{ title: t("nav.home"), tabBarIcon: makeIcon("home-variant") }}
      />
      <Tabs.Screen
        name="places"
        options={{ title: "Luoghi", tabBarIcon: makeIcon("map-marker-radius") }}
      />
      <Tabs.Screen
        name="map"
        options={{ title: "Itinerario", tabBarIcon: makeIcon("map-marker-path") }}
      />
      <Tabs.Screen
        name="itineraries"
        options={{ href: null }}
      />
      <Tabs.Screen
        name="info"
        options={{ title: "Info", tabBarIcon: makeIcon("information-outline") }}
      />
    </Tabs>
  );
}
