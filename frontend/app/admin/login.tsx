import React, { useState } from "react";
import { View, Text } from "react-native";
import { KeyboardAwareScrollView } from "react-native-keyboard-controller";
import { router } from "expo-router";
import { useTranslation } from "react-i18next";

import { Header } from "@/src/components/Header";
import { Button, Card, Field, useToast } from "@/src/components/ui";
import { Icon } from "@/src/components/Icon";
import { makeStyles, useTheme } from "@/src/theme";
import { fonts, radius, spacing } from "@/src/lib/typography";
import { useAuth } from "@/src/lib/auth";

export default function AdminLogin() {
  const { t } = useTranslation();
  const s = useStyles();
  const { colors } = useTheme();
  const toast = useToast();
  const { login } = useAuth();
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [loading, setLoading] = useState(false);

  const submit = async () => {
    if (!username.trim() || !password.trim()) return;
    setLoading(true);
    try {
      await login(username.trim(), password);
      toast.show("Benvenuto!", "success");
      router.replace("/admin");
    } catch {
      toast.show("Credenziali non valide", "error");
    } finally {
      setLoading(false);
    }
  };

  return (
    <View style={s.screen}>
      <Header title={t("nav.login")} showBack showLang={false} />
      <KeyboardAwareScrollView contentContainerStyle={{ padding: spacing.md, flexGrow: 1, justifyContent: "center" }} bottomOffset={20}>
        <View style={s.logoWrap}>
          <View style={s.logo}>
            <Icon name="shield-account" size={40} color={colors.onBrandPrimary} />
          </View>
          <Text style={s.title}>Area Amministratore</Text>
          <Text style={s.subtitle}>Gestisci prenotazioni, prezzi e contenuti</Text>
        </View>
        <Card style={{ gap: spacing.sm }}>
          <Field value={username} onChangeText={setUsername} placeholder="Username" icon="account-outline" autoCapitalize="none" testID="admin-username" />
          <Field value={password} onChangeText={setPassword} placeholder="Password" icon="lock-outline" secureTextEntry testID="admin-password" />
          <Button testID="admin-login-submit" label={t("nav.login")} icon="login" onPress={submit} loading={loading} />
        </Card>
      </KeyboardAwareScrollView>
    </View>
  );
}

const useStyles = makeStyles((c) => ({
  screen: { flex: 1, backgroundColor: c.surface },
  logoWrap: { alignItems: "center", marginBottom: spacing.xl, gap: spacing.sm },
  logo: { width: 84, height: 84, borderRadius: radius.pill, backgroundColor: c.brandPrimary, alignItems: "center", justifyContent: "center" },
  title: { color: c.onSurface, fontSize: 26, fontFamily: fonts.heading, marginTop: spacing.sm },
  subtitle: { color: c.muted, fontSize: 14, fontFamily: fonts.body, textAlign: "center" },
}));
